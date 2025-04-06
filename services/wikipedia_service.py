import requests
from typing import List, Dict, Optional, Union
import time
from functools import lru_cache
import json
import random
import logging

# Настраиваем логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WikipediaHelper:
    def __init__(self, lang: str = "ru"):
        self.lang = lang
        self.wikidata_endpoint = "https://www.wikidata.org/w/api.php"
        self.wikipedia_endpoint = f"https://{lang}.wikipedia.org/w/api.php"
        self.sparql_endpoint = "https://query.wikidata.org/sparql"
        
    @lru_cache(maxsize=1000)
    def _make_request(self, endpoint: str, params_str: str) -> Dict:
        """Make a cached request to the API endpoint"""
        try:
            params = json.loads(params_str)
            logger.info(f"Making request to {endpoint} with params: {params}")
            response = requests.get(endpoint, params=params, timeout=5)
            response.raise_for_status()
            result = response.json()
            logger.info(f"Response received: {json.dumps(result, indent=2)}")
            return result
        except requests.RequestException as e:
            logger.error(f"Error making request: {e}")
            return {"error": str(e)}

    def _make_sparql_request(self, query: str) -> Dict:
        """Make a request to the SPARQL endpoint"""
        try:
            logger.info(f"Making SPARQL request: {query}")
            response = requests.get(
                self.sparql_endpoint,
                params={"format": "json", "query": query},
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"SPARQL response received: {json.dumps(result, indent=2)}")
            return result
        except requests.RequestException as e:
            logger.error(f"Error making SPARQL request: {e}")
            return {"error": str(e)}

    def search(self, query: str) -> List[Dict]:
        """Search for entities using Wikidata"""
        search_params = {
            "action": "wbsearchentities",
            "format": "json",
            "language": self.lang,
            "search": query,
            "type": "item"
        }
        
        results = self._make_request(self.wikidata_endpoint, json.dumps(search_params, sort_keys=True))
        valid_results = []
        
        if "search" not in results:
            logger.warning(f"No search results found for query: {query}")
            return valid_results
            
        for item in results["search"]:
            entity_type = self._get_entity_type(item["id"])
            if entity_type in ["fictional", "real"]:
                valid_results.append({
                    "id": item["id"],
                    "name": item["label"],
                    "type": entity_type,
                    "description": item.get("description", ""),
                    "url": f"https://www.wikidata.org/wiki/{item['id']}"  # Всегда добавляем URL Wikidata
                })
                
        logger.info(f"Found {len(valid_results)} valid results for query: {query}")
        return valid_results

    def _get_entity_type(self, entity_id: str) -> str:
        """Determine if entity is fictional or real person"""
        params = {
            "action": "wbgetclaims",
            "format": "json",
            "entity": entity_id,
            "property": "P31"  # instance of
        }
        
        claims = self._make_request(self.wikidata_endpoint, json.dumps(params, sort_keys=True))
        
        if "error" in claims:
            logger.error(f"Error getting claims for entity {entity_id}: {claims['error']}")
            return "other"
            
        if "claims" not in claims or "P31" not in claims["claims"]:
            logger.warning(f"No claims found for entity {entity_id}")
            return "other"
            
        # Q5 = human
        # Q15632617 = fictional human
        # Q15632618 = fictional character
        instance_of = [claim["mainsnak"]["datavalue"]["value"]["id"] 
                      for claim in claims["claims"]["P31"]]
        
        logger.info(f"Entity {entity_id} instance_of: {instance_of}")
                      
        if "Q5" in instance_of:
            return "real"
        elif any(q in instance_of for q in ["Q15632617", "Q15632618"]):
            return "fictional"
            
        return "other"

    def get_wikipedia_info(self, query: str) -> Dict:
        """Get detailed information about an entity"""
        search_results = self.search(query)
        
        if not search_results:
            logger.warning(f"No results found for query: {query}")
            return {
                "status": "not_found",
                "name": query,
                "summary": "Информация не найдена."
            }
            
        if len(search_results) == 1:
            return self._get_entity_details(search_results[0])
        else:
            return {
                "status": "multiple_results",
                "results": search_results
            }

    def _get_entity_details(self, entity: Dict) -> Dict:
        """Get detailed information about a specific entity"""
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": entity["id"],
            "languages": self.lang,
            "props": "labels|descriptions|claims|sitelinks"
        }
        
        result = self._make_request(self.wikidata_endpoint, json.dumps(params, sort_keys=True))
        
        if "error" in result or "entities" not in result:
            logger.error(f"Error getting entity details for {entity['id']}: {result.get('error', 'Unknown error')}")
            return {
                "status": "error",
                "name": entity["name"],
                "summary": "Ошибка при получении данных."
            }
            
        entity_data = result["entities"][entity["id"]]
        
        # Get Wikipedia article URL
        wiki_url = None
        if "sitelinks" in entity_data and f"{self.lang}wiki" in entity_data["sitelinks"]:
            wiki_url = f"https://{self.lang}.wikipedia.org/wiki/{entity_data['sitelinks'][f'{self.lang}wiki']['title'].replace(' ', '_')}"
            
        # Get description
        description = entity_data.get("descriptions", {}).get(self.lang, {}).get("value", "")
        
        logger.info(f"Got details for entity {entity['id']}: {description[:100]}...")
        
        # Always provide a fallback URL to Wikidata
        wikidata_url = f"https://www.wikidata.org/wiki/{entity['id']}"
        
        return {
            "status": "ok",
            "name": entity["name"],
            "type": entity["type"],
            "summary": description,
            "url": wiki_url or wikidata_url,  # Use Wikipedia URL if available, otherwise use Wikidata URL
            "wikidata_id": entity["id"]
        }

    def get_random(self, type: str) -> Optional[Dict]:
        """Get a random entity of specified type"""
        logger.info(f"Getting random entity of type: {type}")
        
        # Получаем случайную статью через Wikipedia API
        params = {
            "action": "query",
            "format": "json",
            "list": "random",
            "rnnamespace": "0",  # только основные статьи
            "rnlimit": "10"  # получаем несколько статей для выбора
        }
        
        result = self._make_request(self.wikipedia_endpoint, json.dumps(params, sort_keys=True))
        
        if "error" in result:
            logger.error(f"Error getting random article: {result['error']}")
            return None
            
        if "query" not in result or "random" not in result["query"]:
            logger.error("No random articles in response")
            return None
            
        random_articles = result["query"]["random"]
        logger.info(f"Found {len(random_articles)} random articles")
        
        # Пробуем найти подходящую статью нужного типа
        for article in random_articles:
            title = article["title"]
            logger.info(f"Checking article: {title}")
            
            # Ищем статью в Wikidata
            search_params = {
                "action": "wbsearchentities",
                "format": "json",
                "language": self.lang,
                "search": title,
                "type": "item"
            }
            
            search_result = self._make_request(self.wikidata_endpoint, json.dumps(search_params, sort_keys=True))
            
            if "search" not in search_result:
                continue
                
            for item in search_result["search"]:
                entity_type = self._get_entity_type(item["id"])
                if entity_type == type:
                    logger.info(f"Found matching entity: {item['label']} ({entity_type})")
                    return self._get_entity_details({
                        "id": item["id"],
                        "name": item["label"],
                        "type": entity_type,
                        "description": item.get("description", "")
                    })
        
        logger.warning("No suitable random entity found")
        return None
