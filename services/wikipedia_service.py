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
        if not query or not query.strip():
            logger.warning("Empty search query")
            return []
            
        search_params = {
            "action": "wbsearchentities",
            "format": "json",
            "language": self.lang,
            "search": query,
            "type": "item",
            "limit": 20  # Increase limit to get more results
        }
        
        results = self._make_request(self.wikidata_endpoint, json.dumps(search_params, sort_keys=True))
        valid_results = []
        
        if "error" in results:
            logger.error(f"Error in search results: {results['error']}")
            return valid_results
            
        if "search" not in results:
            logger.warning(f"No search results found for query: {query}")
            return valid_results

        for item in results["search"]:
            try:
                entity_type = self._get_entity_type(item["id"])
                if entity_type in ["fictional", "real"]:
                    # Ensure all required fields are present
                    name = item.get("label", "Без имени")
                    description = item.get("description", "")
                    
                    valid_results.append({
                        "id": item["id"],
                        "name": name,
                        "type": entity_type,
                        "description": description,
                        "url": f"https://www.wikidata.org/wiki/{item['id']}"
                    })
            except Exception as e:
                logger.error(f"Error processing search result {item.get('id', 'unknown')}: {e}")
                continue

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
        # Q95074 = fictional character
        # Q4167410 = fictional character
        instance_of = [claim["mainsnak"]["datavalue"]["value"]["id"] 
                      for claim in claims["claims"]["P31"]]
        
        logger.info(f"Entity {entity_id} instance_of: {instance_of}")
                      
        if "Q5" in instance_of:
            return "real"
        elif any(q in instance_of for q in ["Q15632617", "Q15632618", "Q95074", "Q4167410"]):
            return "fictional"
            
        # Check for additional properties that might indicate a fictional character
        if "claims" in claims:
            # P1191 = date of first performance
            # P1441 = present in work
            # P179 = part of the series
            fictional_indicators = ["P1191", "P1441", "P179"]
            for indicator in fictional_indicators:
                if indicator in claims["claims"]:
                    return "fictional"
            
            return "other"

    def get_wikipedia_info(self, query: str) -> Dict:
        """Get detailed information about an entity"""
        if not query or not query.strip():
            logger.warning("Empty query in get_wikipedia_info")
            return {
                "status": "not_found",
                "name": "",
                "summary": "Пожалуйста, введите поисковый запрос."
            }
            
        search_results = self.search(query)

        if not search_results:
            logger.warning(f"No results found for query: {query}")
            return {
                "status": "not_found",
                "name": query,
                "summary": "Информация не найдена."
            }

        if len(search_results) == 1:
            try:
                return self._get_entity_details(search_results[0])
            except Exception as e:
                logger.error(f"Error getting entity details: {e}")
                return {
                    "status": "error",
                    "name": search_results[0].get("name", query),
                    "summary": "Ошибка при получении данных."
                }
        else:
            return {
                "status": "multiple_results",
                "results": search_results
            }

    def _format_date(self, date_str: str) -> str:
        """Format date from Wikidata format to readable format"""
        if not date_str:
            return None
            
        try:
            # Remove leading + if exists and split by T
            date_str = date_str.lstrip('+').split('T')[0]
            
            # Split into year, month, day
            parts = date_str.split('-')
            year = parts[0].lstrip('0')  # Remove leading zeros from year
            
            # Handle negative years (до н.э.)
            is_bc = year.startswith('-')
            if is_bc:
                year = year[1:]  # Remove minus sign
                
            # If we have month and day
            if len(parts) > 2:
                month = parts[1].lstrip('0') or '1'  # Remove leading zeros, default to 1
                day = parts[2].lstrip('0') or '1'    # Remove leading zeros, default to 1
                
                # Convert to integers to remove unnecessary precision
                year = int(year)
                month = int(month)
                day = int(day)
                
                # Russian month names
                months = [
                    'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
                ]
                
                date_str = f"{day} {months[month-1]} {year}"
                if is_bc:
                    date_str += " до н.э."
                    
                return date_str
            
            # If we only have year
            year = int(year)
            if is_bc:
                return f"{year} до н.э."
            return str(year)
            
        except (ValueError, IndexError) as e:
            logger.error(f"Error formatting date {date_str}: {e}")
            # Try to extract just the year if possible
            try:
                if date_str.startswith('-'):
                    return f"{date_str[1:]} до н.э."
                return date_str.split('T')[0].split('-')[0].lstrip('+')
            except:
                return None

    def _get_entity_details(self, entity: Dict) -> Dict:
        """Get detailed information about a specific entity"""
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": entity["id"],
            "languages": self.lang,
            "props": "labels|descriptions|claims|sitelinks|aliases"
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
        
        # Get name from labels or aliases
        name = None
        if "labels" in entity_data and self.lang in entity_data["labels"]:
            name = entity_data["labels"][self.lang]["value"]
        elif "aliases" in entity_data and self.lang in entity_data["aliases"]:
            name = entity_data["aliases"][self.lang][0]["value"]
        else:
            name = entity["name"]  # Fallback to original name
            
        # Get description from multiple sources
        description = None
        
        # 1. Try to get from descriptions
        if "descriptions" in entity_data and self.lang in entity_data["descriptions"]:
            description = entity_data["descriptions"][self.lang]["value"]
            
        # 2. Try to get from claims
        if not description:
            claims = entity_data.get("claims", {})
            
            # Occupation (P106)
            occupation = None
            if "P106" in claims:
                occupation_ids = [claim["mainsnak"]["datavalue"]["value"]["id"] for claim in claims["P106"]]
                occupation_labels = self._get_entity_labels(occupation_ids)
                if occupation_labels:
                    occupation = ", ".join(occupation_labels)
                    
            # Known for (P737)
            known_for = None
            if "P737" in claims:
                known_for_ids = [claim["mainsnak"]["datavalue"]["value"]["id"] for claim in claims["P737"]]
                known_for_labels = self._get_entity_labels(known_for_ids)
                if known_for_labels:
                    known_for = ", ".join(known_for_labels)
                    
            # Create description from claims
            description_parts = []
            if occupation:
                description_parts.append(f"{name} - {occupation}")
            if known_for:
                description_parts.append(f"известен как {known_for}")
                
            if description_parts:
                description = ". ".join(description_parts)
                
        # 3. If still no description, create a basic one
        if not description:
            entity_type = entity.get("type", "персонаж")
            if entity_type == "fictional":
                description = f"{name} - вымышленный персонаж"
            else:
                description = f"{name} - историческая личность"
        
        # Get Wikipedia article URL
        wiki_url = None
        if "sitelinks" in entity_data and f"{self.lang}wiki" in entity_data["sitelinks"]:
            wiki_url = f"https://{self.lang}.wikipedia.org/wiki/{entity_data['sitelinks'][f'{self.lang}wiki']['title'].replace(' ', '_')}"
            
        # Extract additional information from claims
        claims = entity_data.get("claims", {})
        
        # Occupation (P106)
        occupation = None
        if "P106" in claims:
            occupation_ids = [claim["mainsnak"]["datavalue"]["value"]["id"] for claim in claims["P106"]]
            occupation_labels = self._get_entity_labels(occupation_ids)
            if occupation_labels:
                occupation = ", ".join(occupation_labels)
        
        # Birth date (P569)
        birth_date = None
        if "P569" in claims:
            birth_date = claims["P569"][0]["mainsnak"]["datavalue"]["value"]["time"]
            birth_date = self._format_date(birth_date)
        
        # Death date (P570)
        death_date = None
        if "P570" in claims:
            death_date = claims["P570"][0]["mainsnak"]["datavalue"]["value"]["time"]
            death_date = self._format_date(death_date)
        
        # Nationality (P27)
        nationality = None
        if "P27" in claims:
            nationality_ids = [claim["mainsnak"]["datavalue"]["value"]["id"] for claim in claims["P27"]]
            nationality_labels = self._get_entity_labels(nationality_ids)
            if nationality_labels:
                nationality = ", ".join(nationality_labels)
        
        # Known for (P737)
        known_for = None
        if "P737" in claims:
            known_for_ids = [claim["mainsnak"]["datavalue"]["value"]["id"] for claim in claims["P737"]]
            known_for_labels = self._get_entity_labels(known_for_ids)
            if known_for_labels:
                known_for = ", ".join(known_for_labels)
        
        # Get images (P18)
        images = []
        if "P18" in claims:
            for claim in claims["P18"]:
                image_name = claim["mainsnak"]["datavalue"]["value"]
                image_url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{image_name}"
                images.append({"url": image_url})
        
        # Additional fields for more comprehensive information
        # Gender (P21)
        gender = None
        if "P21" in claims:
            gender_id = claims["P21"][0]["mainsnak"]["datavalue"]["value"]["id"]
            gender_labels = self._get_entity_labels([gender_id])
            if gender_labels:
                gender = gender_labels[0]
        
        # Place of birth (P19)
        place_of_birth = None
        if "P19" in claims:
            place_id = claims["P19"][0]["mainsnak"]["datavalue"]["value"]["id"]
            place_labels = self._get_entity_labels([place_id])
            if place_labels:
                place_of_birth = place_labels[0]
        
        # Place of death (P20)
        place_of_death = None
        if "P20" in claims:
            place_id = claims["P20"][0]["mainsnak"]["datavalue"]["value"]["id"]
            place_labels = self._get_entity_labels([place_id])
            if place_labels:
                place_of_death = place_labels[0]
        
        # Languages spoken (P1412)
        languages = None
        if "P1412" in claims:
            language_ids = [claim["mainsnak"]["datavalue"]["value"]["id"] for claim in claims["P1412"]]
            language_labels = self._get_entity_labels(language_ids)
            if language_labels:
                languages = ", ".join(language_labels)
        
        # Awards (P166)
        awards = None
        if "P166" in claims:
            award_ids = [claim["mainsnak"]["datavalue"]["value"]["id"] for claim in claims["P166"]]
            award_labels = self._get_entity_labels(award_ids)
            if award_labels:
                awards = ", ".join(award_labels)
        
        logger.info(f"Got details for entity {entity['id']}: {description[:100]}...")
        
        # Always provide a fallback URL to Wikidata
        wikidata_url = f"https://www.wikidata.org/wiki/{entity['id']}"
        
        return {
            "status": "ok",
            "name": name,
            "type": entity["type"],
            "summary": description,
            "url": wiki_url or wikidata_url,
            "wikidata_id": entity["id"],
            "occupation": occupation,
            "birth_date": birth_date,
            "death_date": death_date,
            "nationality": nationality,
            "known_for": known_for,
            "images": images[:4],  # Limit to 4 images
            "gender": gender,
            "place_of_birth": place_of_birth,
            "place_of_death": place_of_death,
            "languages": languages,
            "awards": awards
        }
        
    def _get_entity_labels(self, entity_ids: List[str]) -> List[str]:
        """Get labels for multiple entities"""
        if not entity_ids:
            return []
            
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(entity_ids),
            "languages": self.lang,
            "props": "labels"
        }
        
        result = self._make_request(self.wikidata_endpoint, json.dumps(params, sort_keys=True))
        
        if "error" in result or "entities" not in result:
            return []
            
        labels = []
        for entity_id in entity_ids:
            if entity_id in result["entities"]:
                entity = result["entities"][entity_id]
                if "labels" in entity and self.lang in entity["labels"]:
                    labels.append(entity["labels"][self.lang]["value"])
                    
        return labels

    def get_random(self, type: str) -> Optional[Dict]:
        """Get a random entity of specified type"""
        logger.info(f"Getting random entity of type: {type}")
        
        if type not in ["fictional", "real"]:
            logger.error(f"Invalid entity type: {type}")
            return None
        
        # Используем SPARQL для получения случайной сущности нужного типа
        if type == "real":
            # Для реальных людей
            sparql_query = """
            SELECT ?item ?itemLabel WHERE {
              ?item wdt:P31 wd:Q5 .
              SERVICE wikibase:label { bd:serviceParam wikibase:language "ru,en". }
              ?item rdfs:label ?itemLabel .
              FILTER(LANG(?itemLabel) = "ru")
            }
            ORDER BY RAND()
            LIMIT 10
            """
        else:
            # Для вымышленных персонажей
            sparql_query = """
            SELECT ?item ?itemLabel WHERE {
              ?item wdt:P31 ?type .
              VALUES ?type { wd:Q15632617 wd:Q15632618 wd:Q95074 wd:Q4167410 }
              SERVICE wikibase:label { bd:serviceParam wikibase:language "ru,en". }
              ?item rdfs:label ?itemLabel .
              FILTER(LANG(?itemLabel) = "ru")
            }
            ORDER BY RAND()
            LIMIT 10
            """
        
        result = self._make_sparql_request(sparql_query)
        
        if "error" in result:
            logger.error(f"Error in SPARQL query: {result['error']}")
            return None
            
        if "results" not in result or "bindings" not in result["results"] or not result["results"]["bindings"]:
            logger.warning("No results from SPARQL query")
            return None
            
        # Выбираем случайный результат
        bindings = result["results"]["bindings"]
        if not bindings:
            logger.warning("Empty bindings from SPARQL query")
            return None
            
        random_item = random.choice(bindings)
        entity_id = random_item["item"]["value"].split("/")[-1]
        entity_name = random_item["itemLabel"]["value"]
        
        logger.info(f"Found random entity: {entity_name} ({entity_id})")
        
        # Получаем детали сущности
        return self._get_entity_details({
            "id": entity_id,
            "name": entity_name,
            "type": type,
            "description": ""
        })

    def get_entity_by_id(self, entity_id: str) -> Optional[Dict]:
        """Get detailed information about an entity by its ID"""
        logger.info(f"Getting entity details by ID: {entity_id}")
        
        try:
            # Определяем тип сущности
            entity_type = self._get_entity_type(entity_id)
            
            # Создаем объект с базовой информацией
            entity = {
                "id": entity_id,
                "name": "",  # Будет заполнено из ответа API
                "type": entity_type,
                "description": ""
            }
            
            # Получаем детали сущности
            result = self._get_entity_details(entity)
            
            if result and result.get("status") == "ok":
                return result
            else:
                logger.warning(f"Failed to get entity details for ID: {entity_id}")
                return None

        except Exception as e:
            logger.error(f"Error getting entity by ID: {e}")
            return None
