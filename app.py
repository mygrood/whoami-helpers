from flask import Flask, render_template, request, redirect, url_for, jsonify
from services.wikipedia_service import WikipediaHelper
import time
import logging
import traceback
import random

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
wikipedia_helper = WikipediaHelper()

# Список известных персонажей для использования в качестве запасного варианта
FALLBACK_CHARACTERS = {
    "real": [
        {"id": "Q5", "name": "Человек", "type": "real", "description": "Человек разумный"},
        {"id": "Q937", "name": "Альберт Эйнштейн", "type": "real", "description": "Физик-теоретик"},
        {"id": "Q14211", "name": "Леонардо да Винчи", "type": "real", "description": "Итальянский художник, учёный, изобретатель"},
        {"id": "Q33977", "name": "Уильям Шекспир", "type": "real", "description": "Английский драматург и поэт"},
        {"id": "Q10261", "name": "Наполеон Бонапарт", "type": "real", "description": "Французский император"}
    ],
    "fictional": [
        {"id": "Q15632617", "name": "Гарри Поттер", "type": "fictional", "description": "Вымышленный персонаж, волшебник"},
        {"id": "Q15632618", "name": "Шерлок Холмс", "type": "fictional", "description": "Вымышленный детектив"},
        {"id": "Q95074", "name": "Джеймс Бонд", "type": "fictional", "description": "Вымышленный агент разведки"},
        {"id": "Q4167410", "name": "Дарт Вейдер", "type": "fictional", "description": "Вымышленный персонаж из Звёздных войн"},
        {"id": "Q15632619", "name": "Бэтмен", "type": "fictional", "description": "Вымышленный супергерой"}
    ]
}

@app.route('/')
def index():
    logger.info("Rendering index page")
    return render_template('index.html')

@app.route('/search')
def search_character():
    query = request.args.get('query', '').strip()
    entity_id = request.args.get('id', '')
    
    logger.info(f"Search request - query: '{query}', entity_id: '{entity_id}'")
    
    if not query and not entity_id:
        logger.info("Empty search request, redirecting to index")
        return redirect(url_for('index'))
    
    # Если указан ID, получаем информацию о конкретном персонаже
    if entity_id:
        try:
            logger.info(f"Fetching entity by ID: {entity_id}")
            character_info = wikipedia_helper.get_entity_by_id(entity_id)
            if character_info and character_info.get('status') == 'ok':
                logger.info(f"Successfully fetched character: {character_info.get('name', 'Unknown')}")
                return render_template('character.html', character=character_info)
            else:
                logger.warning(f"Failed to get character info for ID: {entity_id}")
                return render_template('not_found.html', 
                                    query=query or "персонаж",
                                    error_message="Не удалось получить информацию о персонаже.")
        except Exception as e:
            logger.error(f"Error getting entity by ID: {e}")
            logger.error(traceback.format_exc())
            return render_template('not_found.html', 
                                query=query or "персонаж",
                                error_message="Произошла ошибка при получении данных.")
        
    # Иначе выполняем поиск по запросу
    try:
        logger.info(f"Searching for character: {query}")
        character_info = wikipedia_helper.get_wikipedia_info(query)
        
        if character_info['status'] == "multiple_results":
            logger.info(f"Found multiple results for query: {query}")
            return render_template('multiple_search.html', 
                                results=character_info['results'],
                                query=query)
        elif character_info['status'] == "ok":
            logger.info(f"Found single result for query: {query}")
            return render_template('character.html', 
                                character=character_info)
        elif character_info['status'] == "error":
            logger.warning(f"Error in search results for query: {query}")
            return render_template('not_found.html', 
                                query=query,
                                error_message=character_info.get('summary', 'Произошла ошибка при поиске.'))
        else:
            logger.warning(f"No results found for query: {query}")
            return render_template('not_found.html', 
                                query=query)
    except Exception as e:
        logger.error(f"Error during search: {e}")
        logger.error(traceback.format_exc())
        return render_template('not_found.html', 
                            query=query,
                            error_message="Произошла ошибка при выполнении поиска.")

@app.route('/random/<type>')
def random_character(type):
    logger.info(f"Request for random character of type: {type}")
    # Показываем анимацию загрузки
    return render_template('loading.html', type=type)

@app.route('/api/random/<type>')
def api_random_character(type):
    logger.info(f"API request for random character of type: {type}")
    start_time = time.time()
    
    try:
        # Имитируем задержку для демонстрации анимации
        time.sleep(1.5)
        
        logger.info(f"Fetching random character of type: {type}")
        character_info = wikipedia_helper.get_random(type)
        
        if not character_info:
            logger.warning(f"No random character found for type: {type}, using fallback")
            # Используем запасной вариант, если не удалось получить случайного персонажа
            if type in FALLBACK_CHARACTERS:
                fallback_char = random.choice(FALLBACK_CHARACTERS[type])
                logger.info(f"Using fallback character: {fallback_char['name']}")
                
                # Получаем детали для запасного персонажа
                character_info = wikipedia_helper.get_entity_by_id(fallback_char['id'])
                
                if not character_info or character_info.get('status') != 'ok':
                    # Если не удалось получить детали, создаем базовую информацию
                    character_info = {
                        "status": "ok",
                        "name": fallback_char['name'],
                        "type": fallback_char['type'],
                        "summary": fallback_char['description'],
                        "url": f"https://www.wikidata.org/wiki/{fallback_char['id']}",
                        "wikidata_id": fallback_char['id']
                    }
            else:
                return jsonify({"error": "Не удалось найти персонажа"}), 404
        
        elapsed_time = time.time() - start_time
        logger.info(f"Successfully fetched random character: {character_info.get('name', 'Unknown')} in {elapsed_time:.2f} seconds")
        return jsonify(character_info)
    except Exception as e:
        logger.error(f"Error fetching random character: {e}")
        logger.error(traceback.format_exc())
        
        # Используем запасной вариант в случае ошибки
        if type in FALLBACK_CHARACTERS:
            fallback_char = random.choice(FALLBACK_CHARACTERS[type])
            logger.info(f"Using fallback character after error: {fallback_char['name']}")
            
            # Создаем базовую информацию
            character_info = {
                "status": "ok",
                "name": fallback_char['name'],
                "type": fallback_char['type'],
                "summary": fallback_char['description'],
                "url": f"https://www.wikidata.org/wiki/{fallback_char['id']}",
                "wikidata_id": fallback_char['id']
            }
            
            return jsonify(character_info)
        
        return jsonify({"error": "Произошла ошибка при генерации персонажа"}), 500

@app.errorhandler(404)
def page_not_found(e):
    logger.warning(f"Page not found: {request.path}")
    return render_template('not_found.html', 
                         query=request.path), 404

@app.errorhandler(500)
def internal_server_error(e):
    logger.error(f"Internal server error: {e}")
    logger.error(traceback.format_exc())
    return render_template('not_found.html', 
                         query="произошла ошибка",
                         error_message="Внутренняя ошибка сервера. Пожалуйста, попробуйте позже."), 500

if __name__ == '__main__':
    app.run(debug=True)

