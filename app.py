from flask import Flask, render_template, request, redirect, url_for
from services.wikipedia_service import WikipediaHelper
import time

app = Flask(__name__)
wikipedia_helper = WikipediaHelper()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search')
def search_character():
    query = request.args.get('query', '').strip()
    
    if not query:
        return redirect(url_for('index'))
        
    try:
        character_info = wikipedia_helper.get_wikipedia_info(query)
        
        if character_info['status'] == "multiple_results":
            return render_template('multiple_search.html', 
                                results=character_info['results'],
                                query=query)
        elif character_info['status'] == "ok":
            return render_template('character.html', 
                                character=character_info)
        else:
            return render_template('not_found.html', 
                                query=query)
    except Exception as e:
        print(f"Error during search: {e}")
        return render_template('not_found.html', 
                            query=query)

@app.route('/random/<type>')
def random_character(type):
    if type not in ['fictional', 'real']:
        return redirect(url_for('index'))
        
    try:
        start_time = time.time()
        character = wikipedia_helper.get_random(type)
        
        if character is None:
            return render_template('not_found.html', 
                                query=f"случайный {type}")
                                
        # Если поиск занял больше 5 секунд, показываем сообщение
        if time.time() - start_time > 5:
            return render_template('character.html', 
                                character=character,
                                slow_search=True)
                                
        return render_template('character.html', 
                            character=character)
    except Exception as e:
        print(f"Error getting random character: {e}")
        return render_template('not_found.html', 
                            query=f"случайный {type}")

@app.errorhandler(404)
def page_not_found(e):
    return render_template('not_found.html', 
                         query=request.path), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('not_found.html', 
                         query="произошла ошибка"), 500

if __name__ == '__main__':
    app.run(debug=True)

