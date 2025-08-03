from flask import Flask, jsonify, request, render_template, abort, send_from_directory, redirect, url_for, make_response, g
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from functools import wraps
import animeflv as animeflv
import requests
import time
import os
import uuid
import json
import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError


app = Flask(__name__)

# JWT Configuration
app.config['SECRET_KEY'] = 'your-secret-key-1234'  # In production, use environment variable
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(seconds=30)  # Token expires in 30 seconds para pruebas rápidas

# Admin credentials (in production, store hashed passwords in a database)
ADMIN_CREDENTIALS = {
    'username': '1234',
    'password': '1234'  # In production, store hashed passwords
}

# Configuration
ANILIST_GRAPHQL = 'https://graphql.anilist.co'
ITEMS_PER_PAGE = 50  
MAX_PAGES = 3  
HEADERS = {}

# Wallhaven configuration
WALLHAVEN_API_URL = 'https://wallhaven.cc/api/v1/search'
WALLHAVEN_HEADERS = {
    'Accept': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Categories for anime wallpapers
WALLHAVEN_CATEGORIES = '110'  # Anime category only
WALLHAVEN_PURITY = '110'      # SFW only
WALLHAVEN_SORTING = 'relevance'
WALLHAVEN_TOP_RANGE = '1M'     # Top wallpapers from last month
WALLHAVEN_ATLEAST = '1920x1080'  # Minimum resolution

def get_anime_wallpaper(anime_name):
    """Search Wallhaven for high-quality wallpapers ONLY. Never use thumbnails."""
    try:
        # Clean the anime name for search
        search_query = anime_name.lower().replace(' ', '+')
        
        # Build the search URL with quality options
        params = {
            'q': search_query,
            'categories': WALLHAVEN_CATEGORIES,
            'purity': WALLHAVEN_PURITY,
            'sorting': 'relevance',
            'resolutions': '3840x2160',  # 4K resolution
            'page': 1,
            'apikey': 'wRErqh28bZG5y0iWv48FePYNK2Q6bvp4'  # API key como parámetro
        }
        
        # Headers con User-Agent mejorado
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        print(f"Searching Wallhaven for: {anime_name}")
        print(f"API URL: {WALLHAVEN_API_URL}")
        print(f"Params: {params}")
        
        # Deshabilitar advertencias de solicitudes no verificadas
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        try:
            # Intentar con verificación SSL
            response = requests.get(
                WALLHAVEN_API_URL, 
                params=params, 
                headers=headers, 
                verify=True,
                timeout=10
            )
            response.raise_for_status()
            print("Successfully fetched data with SSL verification")
        except requests.exceptions.SSLError as ssl_err:
            print(f"SSL Error (will retry without verification): {ssl_err}")
            # Si falla, intentar sin verificación SSL
            try:
                response = requests.get(
                    WALLHAVEN_API_URL, 
                    params=params, 
                    headers=headers, 
                    verify=False, 
                    timeout=10
                )
                response.raise_for_status()
                print("Successfully fetched data without SSL verification")
            except Exception as e:
                print(f"Error fetching data even without SSL verification: {e}")
                return None
        except requests.exceptions.RequestException as req_err:
            print(f"Request error: {req_err}")
            return None
            
        try:
            data = response.json()
            print(f"API Response: {data}")
            
            if data.get('data') and len(data['data']) > 0:
                # Get all wallpapers from the response
                wallpapers = data['data']
                
                # Try to find a high-quality wallpaper
                for wallpaper in wallpapers:
                    print(f"Checking wallpaper: {wallpaper}")
                    
                    # First try to get the full URL directly
                    if wallpaper.get('path'):
                        full_url = wallpaper['path']
                        print(f"Found high-quality URL from API: {full_url}")
                        # Devolvemos directamente la URL sin verificación adicional
                        return full_url
                    
                    # Si no hay path, intentamos construir la URL con el ID
                    wallpaper_id = wallpaper.get('id')
                    if wallpaper_id:
                        # Construir la URL en formato directo de Wallhaven
                        direct_url = f"https://w.wallhaven.cc/full/{wallpaper_id[:2]}/wallhaven-{wallpaper_id}.jpg"
                        print(f"Constructed direct URL: {direct_url}")
                        # Devolvemos la URL construida sin verificación
                        return direct_url
                
                print("No accessible high-quality wallpaper found")
                return None
            
            print(f"No wallpapers found for query: {search_query}")
            return None
            
        except ValueError as json_err:
            print(f"Error parsing JSON response: {json_err}")
            print(f"Response content: {response.text[:500]}...")  # Mostrar solo los primeros 500 caracteres
            return None
            
    except Exception as e:
        print(f"Unexpected error in get_anime_wallpaper: {e}")
        return None

# Helper function to check if image is valid
# (This is a simplified version - in production you might want to make a HEAD request to check)
def is_valid_image(url):
    try:
        # Check if URL exists and is an image
        if url and url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
            return True
        return False
    except:
        return False

# JWT Authentication Decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Check for token in Authorization header (for API)
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        # Check for token in cookies (for web)
        elif 'token' in request.cookies:
            token = request.cookies.get('token')
        
        if not token:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': 'Token is missing'}), 401
            return redirect(url_for('login', error='Por favor inicia sesión para continuar'))
        
        try:
            # Decode the token
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = data['username']
            next_page = data.get('next', 'trace')  # Por defecto redirige a trace
            g.next_page = next_page  # Asegurar que esté disponible en el contexto global
            print(f"Token decoded with next_page: {next_page}")  # Debugging
            
            # Add user to the request context
            g.current_user = current_user
            g.next_page = next_page
            
        except ExpiredSignatureError:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': 'La sesión ha expirado'}), 401
            resp = make_response(redirect(url_for('login', error='La sesión ha expirado')))
            resp.set_cookie('token', '', expires=0)
            return resp
            
        except InvalidTokenError:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': 'Token inválido'}), 401
            resp = make_response(redirect(url_for('login', error='Sesión inválida')))
            resp.set_cookie('token', '', expires=0)
            return resp
            
        return f(current_user, *args, **kwargs)
    return decorated

# API Login route (for AJAX requests)
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    next_page = request.args.get('next', 'trace')  # Por defecto redirige a trace
    g.next_page = next_page  # Almacenar en el contexto global para acceso posterior
    print(f"Login requested with next_page: {next_page}")  # Debugging
    
    if not username or not password:
        return jsonify({'success': False, 'message': 'Usuario y contraseña son requeridos'}), 400
    
    if username == ADMIN_CREDENTIALS['username'] and password == ADMIN_CREDENTIALS['password']:
        # Create JWT token
        token = jwt.encode({
            'username': username,
            'exp': datetime.utcnow() + app.config['JWT_ACCESS_TOKEN_EXPIRES'],
            'next': next_page
        }, app.config['SECRET_KEY'])
        
        return jsonify({
            'success': True,
            'message': 'Inicio de sesión exitoso',
            'token': token,
            'user': {
                'username': username
            }
        })
    
    return jsonify({'success': False, 'message': 'Credenciales inválidas'}), 401

# Web Login route (for direct browser access)
@app.route('/login', methods=['GET'])
def login():
    error = request.args.get('error')
    next_page = request.args.get('next', 'trace')  # Por defecto redirige a trace
    return render_template('login.html', error=error, next_page=next_page)

# Logout route
@app.route('/api/logout')
def api_logout():
    resp = jsonify({'success': True, 'message': 'Sesión cerrada correctamente'})
    resp.set_cookie('token', '', expires=0)
    return resp

# Web Logout route
@app.route('/logout')
def logout():
    resp = make_response(redirect(url_for('login')))
    resp.set_cookie('token', '', expires=0)
    return resp

# --- File storage and upload configuration ---
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
DATA_FILE = 'data.json'

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Helper functions
def allowed_file(filename: str) -> bool:
    """Check if filename has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploaded_file(file_storage, anime_id: int, file_type: str) -> str:
    """Save an uploaded file (cover/wallpaper) and return its relative path."""
    ext = secure_filename(file_storage.filename).rsplit('.', 1)[1].lower()
    filename = f"{file_type}_{anime_id}_{uuid.uuid4()}.{ext}"
    path = os.path.join(UPLOAD_FOLDER, filename)
    file_storage.save(path)
    return f"{UPLOAD_FOLDER}/{filename}"


def load_anime_data() -> list:
    """Load anime data from JSON file. Returns empty list if file doesn't exist."""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Accept both list or dict formats
                if isinstance(data, dict) and 'anime' in data:
                    return data['anime']
                elif isinstance(data, list):
                    return data
                else:
                    print(f"Unexpected data format in {DATA_FILE}, expected list or dict with 'anime' key")
                    return []
        except Exception as e:
            print(f"Error loading {DATA_FILE}: {e}")
            return []
    return []


def save_anime_data(data: list) -> None:
    """Persist anime data list to JSON file."""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving {DATA_FILE}: {e}")


@app.route('/')
def catalogo():

    anime_list = []
    error = None
    try:
        api_resp = get_anime_list()

       
        if isinstance(api_resp, tuple):
            resp, status_code = api_resp
        else:
            resp, status_code = api_resp, api_resp.status_code

        if status_code != 200:
            error_json = resp.get_json(silent=True) or {}
            error = error_json.get("error", "Error fetching anime list")
        else:
            payload = resp.get_json(silent=True) or {}
            anime_list = payload.get("animes", [])

    except Exception as e:
        print(f"Unexpected error in catalogo(): {e}")
        error = str(e)

    return render_template("catalogo.html", anime_list=anime_list, error=error)

@app.route('/admin')
def admin():    
    anime_list = load_anime_data()
    return render_template('admin_api.html', anime_list=anime_list)

# API Endpoints
@app.route('/api/anime', methods=['GET'])
def get_anime_list():
    all_anime = []
    current_page = 1
    last_page = None

    try:
        while True:
            query = """
            query ($page: Int, $perPage: Int) {
              Page(page: $page, perPage: $perPage) {
                pageInfo { total currentPage lastPage hasNextPage }
                media(type: ANIME, sort: POPULARITY_DESC) {
                  id
                  idMal
                  title { romaji english native }
                  genres
                  episodes
                  averageScore
                  startDate { year month day }
                  endDate { year month day }
                  studios(isMain: true) { nodes { name } }
                  description(asHtml: false)
                  siteUrl
                  coverImage { large }
                }
              }
            }
            """
            variables = {"page": current_page, "perPage": ITEMS_PER_PAGE}
            print(f"Fetching page {current_page} from AniList")
            try:
             response = requests.post(ANILIST_GRAPHQL, json={"query": query, "variables": variables})
             response.raise_for_status()
            except requests.exceptions.HTTPError as http_err:
             if http_err.response is not None and http_err.response.status_code == 429:
                 print("AniList rate-limit reached (429). Returning partial list.")
                 break  # salimos del bucle con lo que tengamos
             raise
            data = response.json()

            if 'data' not in data or 'Page' not in data['data']:
                raise ValueError('Invalid response structure from AniList')
            page_info = data['data']['Page']['pageInfo']
            anime_data_on_page = data['data']['Page']['media']
            last_page = page_info['lastPage'] 

            for anime in anime_data_on_page:
                title_obj = anime.get('title', {})
                title_en = title_obj.get('english') or title_obj.get('romaji') or title_obj.get('native')
                title_ja = ''

                creator_info = ''

                anime_info = {
                    'id': anime.get('id'), 
                    'nombre': title_en or title_ja or 'Título Desconocido',
                    'genero': ', '.join(anime.get('genres', [])), 
                    'episodios': anime.get('episodes'),
                    'rating': anime.get('averageScore'), 
                    'fecha_lanzamiento': f"{anime.get('startDate', {}).get('year','')}-{anime.get('startDate', {}).get('month','')}-{anime.get('startDate', {}).get('day','')}",
                    'fecha_termino': f"{anime.get('endDate', {}).get('year','')}-{anime.get('endDate', {}).get('month','')}-{anime.get('endDate', {}).get('day','')}",
                    'estudio': ', '.join([studio['name'] for studio in (anime.get('studios', {}).get('nodes', []))]) if anime.get('studios') else '',
                    'synopsis': anime.get('description'),
                    'pagina_web': anime.get('siteUrl', ''),
                    'creador': creator_info, 
                    'imagen': anime.get('coverImage', {}).get('large', ''),
                }
                all_anime.append(anime_info)

            print(f"Fetched {len(anime_data_on_page)} anime from page {current_page}")

            time.sleep(1)

            current_page += 1
            if current_page > last_page or current_page > MAX_PAGES:
                break

        print(f"Finished fetching. Total animes collected: {len(all_anime)}")

        return jsonify({"total_animes": len(all_anime), "animes": all_anime})

    except requests.exceptions.RequestException as e:
        print(f"Network or API error: {e}")
        return jsonify({"error": f"Error al conectar con AniAPI: {e}"}), 500
    except ValueError as e:
        print(f"Data structure error: {e}")
        return jsonify({"error": f"Error en la estructura de la respuesta de AniAPI: {e}"}), 500
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return jsonify({"error": f"Error interno del servidor: {e}"}), 500


@app.route('/api/anime/<int:anime_id>', methods=['GET'])
def get_anime_by_id(anime_id):
    anime_info = None
    
    print(f"Fetching details for anime ID: {anime_id} directly from AniList...")
    try:
        query = """
        query ($id: Int) {
          Media(id: $id, type: ANIME) {
            id
            title { romaji english native }
            genres
            episodes
            averageScore
            startDate { year month day }
            endDate { year month day }
            studios(isMain: true) { nodes { name } }
            description(asHtml: false)
            siteUrl
            coverImage { large }
            staff(sort: [ROLE, RELEVANCE], perPage: 1) { nodes { name { full } } }
          }
        }
        """
        variables = {"id": anime_id}
        response = requests.post(ANILIST_GRAPHQL, json={"query": query, "variables": variables})
        response.raise_for_status()
        data = response.json()

        if 'data' not in data or 'Media' not in data['data']:
            return jsonify({"error": "Invalid response structure from AniList for single anime"}), 500
        
        single_anime_data = data['data']['Media']
        
        title_obj = single_anime_data.get('title', {})
        title_en = title_obj.get('english') or title_obj.get('romaji') or title_obj.get('native')
        title_ja = ''
        
        staff_nodes = single_anime_data.get('staff', {}).get('nodes', [])
        creator_info = staff_nodes[0]['name']['full'] if staff_nodes else ''

        # Obtener todos los títulos
        title_obj = single_anime_data.get('title', {})
        title_romaji = title_obj.get('romaji', '')
        title_english = title_obj.get('english', '')
        title_native = title_obj.get('native', '')
        
        # Usar el título romaji como principal, si está disponible
        main_title = title_romaji or title_english or title_native or 'Título Desconocido'
        
        anime_info = {
            'id': single_anime_data.get('id'),
            'nombre': main_title,
            'title': {
                'romaji': title_romaji,
                'english': title_english,
                'native': title_native
            },
            'title_romaji': title_romaji,  # Para compatibilidad con código existente
            'title_english': title_english,  # Para compatibilidad con código existente
            'title_native': title_native,  # Para compatibilidad con código existente
            'genero': ', '.join(single_anime_data.get('genres', [])),
            'episodios': single_anime_data.get('episodes'),
            'rating': single_anime_data.get('averageScore'),
            'fecha_lanzamiento': f"{single_anime_data.get('startDate', {}).get('year','')}-{single_anime_data.get('startDate', {}).get('month','')}-{single_anime_data.get('startDate', {}).get('day','')}",
            'fecha_termino': f"{single_anime_data.get('endDate', {}).get('year','')}-{single_anime_data.get('endDate', {}).get('month','')}-{single_anime_data.get('endDate', {}).get('day','')}",
            'estudio': ', '.join([studio['name'] for studio in (single_anime_data.get('studios', {}).get('nodes', []))]) if single_anime_data.get('studios') else '',
            'synopsis': single_anime_data.get('description'),
            'pagina_web': single_anime_data.get('siteUrl', ''),
            'creador': creator_info,
            'imagen': single_anime_data.get('coverImage', {}).get('large', ''),
        }

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return jsonify({"error": f"Anime with ID {anime_id} not found on AniList."}), 404
        return jsonify({"error": f"Error fetching from AniList: {e}"}), 500
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Network error connecting to AniList: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

    if not anime_info:
        return jsonify({"error": "Anime not found or no data available."}), 404
    
    # Asegurarse de que los títulos estén disponibles en el nivel superior
    if 'title' in anime_info and isinstance(anime_info['title'], dict):
        anime_info.update({
            'title_romaji': anime_info['title'].get('romaji', ''),
            'title_english': anime_info['title'].get('english', ''),
            'title_native': anime_info['title'].get('native', '')
        })
    
    return jsonify(anime_info)


@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    file_type = request.form.get('type', 'image')
    anime_id = request.form.get('anime_id', '')
    
    if file and allowed_file(file.filename):
        # Generate a unique filename
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{file_type}_{anime_id if anime_id else 'new'}_{uuid.uuid4()}.{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        return jsonify({"filename": f"/{UPLOAD_FOLDER}/{filename}"})
    
    return jsonify({"error": "File type not allowed"}), 400

@app.route('/api/anime', methods=['POST'])
def add_anime():
    # Handle form data with file uploads
    if request.files:
        # Handle file uploads first
        cover_file = request.files.get('cover')
        wallpaper_file = request.files.get('wallpaper')
        form_data = request.form.to_dict()
        
        # Generate new anime ID
        anime_list = load_anime_data()
        new_id = max((a['id'] for a in anime_list), default=0) + 1
        
        # Handle cover image upload
        image_path = ''
        if cover_file and cover_file.filename:
            image_path = save_uploaded_file(cover_file, new_id, 'cover')
        
        # Handle wallpaper upload
        wallpaper_path = ''
        if wallpaper_file and wallpaper_file.filename:
            wallpaper_path = save_uploaded_file(wallpaper_file, new_id, 'wallpaper')
        
        # Create new anime entry
        new_anime = {
            'id': new_id,
            'nombre': form_data.get('title', ''),
            'genero': form_data.get('genre', ''),
            'episodios': int(form_data.get('episodes', 0)),
            'rating': float(form_data.get('rating', 0.0)),
            'fecha_lanzamiento': form_data.get('fecha_lanzamiento', datetime.now().strftime('%Y-%m-%d')),
            'fecha_termino': form_data.get('fecha_termino', ''),
            'estudio': form_data.get('estudio', ''),
            'synopsis': form_data.get('description', form_data.get('synopsis', '')),
            'pagina_web': form_data.get('pagina_web', ''),
            'creador': form_data.get('creador', ''),
            'imagen': image_path,
            'wallpaper': wallpaper_path
        }
        
        anime_list.append(new_anime)
        save_anime_data(anime_list)
        
        return jsonify({"id": new_id, "title": new_anime['nombre']}), 201
    
    # Handle JSON data (for backward compatibility)
    data = request.get_json()
    if not data or not all(key in data for key in ['title', 'genre', 'episodes', 'rating']):
        return jsonify({"error": "Missing required fields"}), 400
    
    anime_list = load_anime_data()
    new_id = max((a['id'] for a in anime_list), default=0) + 1
    
    new_anime = {
        'id': new_id,
        'nombre': data['title'],
        'genero': ', '.join(data['genre']) if isinstance(data['genre'], list) else data['genre'],
        'episodios': data['episodes'],
        'rating': data['rating'],
        'fecha_lanzamiento': datetime.now().strftime('%Y-%m-%d'),
        'fecha_termino': '',
        'estudio': '',
        'synopsis': data.get('description', ''),
        'pagina_web': '',
        'creador': '',
        'imagen': data.get('image', ''),
        'wallpaper': data.get('wallpaper', '')
    }
    
    anime_list.append(new_anime)
    save_anime_data(anime_list)
    
    return jsonify({"id": new_id, "title": data['title']}), 201

@app.route('/api/anime/<int:anime_id>', methods=['PUT'])
def update_anime(anime_id):
    anime_list = load_anime_data()
    anime_index = next((i for i, a in enumerate(anime_list) if a['id'] == anime_id), None)
    if anime_index is None:
        return jsonify({"error": "Anime not found"}), 404
    
    anime = anime_list[anime_index]
    
    # Handle file uploads first
    if request.files:
        # Handle cover image upload
        if 'cover' in request.files:
            cover_file = request.files['cover']
            if cover_file and cover_file.filename != '':
                # Delete old cover if it exists and is not the same as the new one
                if 'imagen' in anime and anime['imagen']:
                    old_image_path = os.path.join('static', anime['imagen'])
                    if os.path.exists(old_image_path):
                        try:
                            os.remove(old_image_path)
                        except Exception as e:
                            print(f"Error deleting old cover: {e}")
                    
                # Save new cover
                image_path = save_uploaded_file(cover_file, anime_id, 'cover')
                if image_path:
                    anime['imagen'] = image_path
        
        # Handle wallpaper upload
        if 'wallpaper' in request.files:
            wallpaper_file = request.files['wallpaper']
            if wallpaper_file and wallpaper_file.filename != '':
                # Delete old wallpaper if it exists and is not the same as the new one
                if 'wallpaper' in anime and anime['wallpaper']:
                    old_wallpaper_path = os.path.join('static', anime['wallpaper'])
                    if os.path.exists(old_wallpaper_path):
                        try:
                            os.remove(old_wallpaper_path)
                        except Exception as e:
                            print(f"Error deleting old wallpaper: {e}")
                
                # Save new wallpaper
                wallpaper_path = save_uploaded_file(wallpaper_file, anime_id, 'wallpaper')
                if wallpaper_path:
                    anime['wallpaper'] = wallpaper_path
    
    # Get form data
    form_data = {}
    if request.form:
        form_data = request.form.to_dict()
    elif request.is_json:
        form_data = request.get_json()
    
    # Update anime fields
    if 'title' in form_data:
        anime['nombre'] = form_data['title']
    if 'genre' in form_data:
        anime['genero'] = form_data['genre']
    if 'synopsis' in form_data or 'description' in form_data:
        anime['synopsis'] = form_data.get('synopsis', form_data.get('description', ''))
    if 'episodes' in form_data:
        try:
            anime['episodios'] = int(form_data['episodes'])
        except (ValueError, TypeError):
            anime['episodios'] = 0
    if 'rating' in form_data:
        try:
            anime['rating'] = float(form_data['rating'])
        except (ValueError, TypeError):
            anime['rating'] = 0.0
    
    # Update additional fields if present
    for field in ['fecha_lanzamiento', 'fecha_termino', 'estudio', 'creador', 'pagina_web']:
        if field in form_data:
            anime[field] = form_data[field]
    
    # Handle current image paths (for when no new file is uploaded)
    if 'current_imagen' in form_data and form_data['current_imagen'] and 'imagen' not in request.files:
        anime['imagen'] = form_data['current_imagen']
    if 'current_wallpaper' in form_data and form_data['current_wallpaper'] and 'wallpaper' not in request.files:
        anime['wallpaper'] = form_data['current_wallpaper']
    
    # Save changes
    anime_list[anime_index] = anime
    save_anime_data(anime_list)
    
    return jsonify(anime), 200

@app.route('/api/anime/<int:anime_id>', methods=['DELETE'])
def delete_anime(anime_id):
    anime_list = load_anime_data()
    anime_to_delete = next((a for a in anime_list if a['id'] == anime_id), None)
    
    if not anime_to_delete:
        return jsonify({"error": "Anime not found"}), 404
    
    # Remove image files if they exist
    try:
        if anime_to_delete.get('imagen'):
            # Handle both full paths and relative paths
            image_path = anime_to_delete['imagen']
            if not image_path.startswith(('http://', 'https://')):
                # If it's a relative path, prepend 'static/' if needed
                if not image_path.startswith(('static/', '/static/')):
                    image_path = os.path.join('static', image_path.lstrip('/'))
                else:
                    image_path = image_path.lstrip('/')
                
                if os.path.exists(image_path):
                    os.remove(image_path)
                    print(f"Deleted image: {image_path}")
        
        if anime_to_delete.get('wallpaper'):
            # Handle both full paths and relative paths
            wallpaper_path = anime_to_delete['wallpaper']
            if not wallpaper_path.startswith(('http://', 'https://')):
                # If it's a relative path, prepend 'static/' if needed
                if not wallpaper_path.startswith(('static/', '/static/')):
                    wallpaper_path = os.path.join('static', wallpaper_path.lstrip('/'))
                else:
                    wallpaper_path = wallpaper_path.lstrip('/')
                
                if os.path.exists(wallpaper_path):
                    os.remove(wallpaper_path)
                    print(f"Deleted wallpaper: {wallpaper_path}")
    except Exception as e:
        print(f"Error deleting files: {e}")
    
    # Remove anime from list
    anime_list = [a for a in anime_list if a['id'] != anime_id]
    
    # Reorder remaining anime IDs
    for index, anime in enumerate(anime_list, 1):
        anime['id'] = index
    
    # Save the updated list with reordered IDs
    save_anime_data(anime_list)
    
    return jsonify({
        "message": "Anime deleted successfully",
        "reordered_ids": True
    })

@app.route('/anime/<int:anime_id>', methods=['GET'])
def anime_detail(anime_id):
    """Render detail page. Looks first in local JSON; if not found, fetches from AniList API.
    Also fetches a reliable Unsplash wallpaper URL"""
    anime_list = load_anime_data()
    anime = next((a for a in anime_list if a['id'] == anime_id), None)
    if not anime:
        api_resp = get_anime_by_id(anime_id)
        if isinstance(api_resp, tuple):
            resp, status_code = api_resp
        else:
            resp, status_code = api_resp, api_resp.status_code
        if status_code == 200:
            anime = resp.get_json(silent=True) or {}
        else:
            return "Anime not found", 404
    
    # Extraer títulos de la respuesta de la API
    if 'title' in anime and isinstance(anime['title'], dict):
        # Extraer títulos principales
        title_data = anime['title']
        
        # Extraer y limpiar títulos
        anime['title_english'] = title_data.get('english')
        anime['title_romaji'] = title_data.get('romaji')
        anime['title_native'] = title_data.get('native')
        
        # Si no hay título en romaji, intentar obtenerlo de otras fuentes
        if not anime['title_romaji']:
            # 1. Intentar obtener del título nativo si está en caracteres romanos
            if anime.get('title_native') and any(c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ' for c in anime['title_native']):
                anime['title_romaji'] = anime['title_native']
            # 2. Usar el título en inglés como respaldo
            elif anime.get('title_english'):
                anime['title_romaji'] = anime['title_english']
        
        # Si no hay título en inglés, usar el romaji
        if not anime['title_english'] and anime['title_romaji']:
            anime['title_english'] = anime['title_romaji']
            
        # Si aún no hay título romaji, usar el nombre del anime
        if not anime['title_romaji'] and anime.get('nombre'):
            anime['title_romaji'] = anime['nombre']
        
        # Debug: Mostrar los títulos extraídos
        print(f"Títulos extraídos - Inglés: {anime.get('title_english')}")
        print(f"Títulos extraídos - Romaji: {anime.get('title_romaji')}")
        print(f"Títulos extraídos - Nativo: {anime.get('title_native')}")
        
        # Asegurarse de que tenemos al menos un título
        if not any([anime.get('title_english'), anime.get('title_romaji'), anime.get('title_native')]):
            print("ADVERTENCIA: No se encontraron títulos en la respuesta de la API")
    else:
        print("ADVERTENCIA: No se encontró el objeto 'title' en la respuesta de la API")

    
    # Obtener información de episodios de AnimeFLV (solo conteo)
    episodes_info = get_episodes_from_animeflv(anime)
    anime['episodes'] = episodes_info
    
    # Guardar el ID de AnimeFLV para usarlo en las descargas
    if episodes_info and len(episodes_info) > 0 and 'animeflv_id' in episodes_info[0]:
        anime['animeflv_id'] = episodes_info[0]['animeflv_id']
        print(f"✅ ID de AnimeFLV guardado: {anime['animeflv_id']}")
    
    # Inicializar episode_links como diccionario vacío ya que no vamos a obtener enlaces
    anime['episode_links'] = {}
    
    # Mostrar información de depuración
    if episodes_info and isinstance(episodes_info, list) and len(episodes_info) > 0:
        print(f"✅ Información de episodios obtenida: {episodes_info[0].get('episode_count', 0)} episodios")
    
    # Obtener wallpaper
    try:
        wallpaper_url = get_anime_wallpaper(anime.get('title_english') or anime.get('title_romaji') or anime.get('nombre', ''))
        if wallpaper_url:
            anime['wallpaper'] = wallpaper_url
        else:
            # Si no se encuentra un wallpaper, usar uno por defecto
            anime['wallpaper'] = "https://w.wallhaven.cc/full/7kx75m/wallpaper-7kx75m.jpg"
    except Exception as e:
        print(f"Error getting wallpaper: {str(e)}")
        anime['wallpaper'] = "https://w.wallhaven.cc/full/7kx75m/wallpaper-7kx75m.jpg"
    
    # Obtener el slug del anime para los enlaces de descarga
    anime_title_for_slug = anime.get('title_romaji') or anime.get('title_english') or anime.get('nombre', '')
    anime_slug = anime_title_for_slug.lower().replace(' ', '-')
    
    # Asegurarse de que el slug solo contenga caracteres válidos
    import re
    anime_slug = re.sub(r'[^a-z0-9-]', '', anime_slug)
    
    # Agregar el slug al diccionario del anime
    anime['slug'] = anime_slug
    
    # Renderizar la plantilla con los datos del anime
    return render_template('anime_detail.html', anime=anime)

def get_episodes_alternative_method(anime_id):
    """
    Método alternativo para obtener episodios mediante scraping directo de la página del anime.
    Se usa como respaldo cuando el método principal de la API falla.
    
    Args:
        anime_id (str): ID del anime en AnimeFLV o slug (ej: 'tokyo-ghoul')
        
    Returns:
        list: Lista de diccionarios con información de los episodios o None si falla
    """
    try:
        # Limpiar el ID del anime (eliminar caracteres no válidos en la URL)
        import re
        anime_id = re.sub(r'[^a-zA-Z0-9-]', '', str(anime_id).lower().replace(' ', '-'))
        
        print(f"\n🔍 Intentando método alternativo para: {anime_id}")
        
        # Construir la URL del anime
        anime_url = f'https://animeflv.net/anime/{anime_id}'
        print(f"  - Solicitando: {anime_url}")
        
        # Configurar headers para simular un navegador
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3',
            'Referer': 'https://www.animeflv.net/',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        }
        
        # Configurar la sesión con reintentos
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        
        # Hacer la petición
        response = session.get(anime_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Verificar que la respuesta sea HTML
        if 'text/html' not in response.headers.get('Content-Type', ''):
            print("  - ❌ La respuesta no es HTML")
            return None
        
        # Parsear el HTML
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Verificar si la página muestra un error 404 o similar
        error_elem = soup.find('div', class_='error404')
        if error_elem:
            print("  - ❌ Página no encontrada (404)")
            return None
        
        # Encontrar la lista de episodios
        episodes_list = soup.select('ul.ListEpisodios li a')
        
        if not episodes_list:
            print("  - ❌ No se encontró la lista de episodios en la página")
            
            # Intentar con un selector alternativo
            episodes_list = soup.select('div.WatchEpisodes a')
            if not episodes_list:
                print("  - ❌ No se encontraron episodios con el selector alternativo")
                return None
        
        episodes = []
        print(f"  - 📺 Se encontraron {len(episodes_list)} episodios")
        
        # Procesar cada episodio (invertir el orden para que sea del 1 en adelante)
        for i, ep in enumerate(reversed(episodes_list), 1):
            try:
                # Obtener la URL del episodio
                episode_path = ep.get('href', '').strip()
                if not episode_path:
                    print(f"  - ❌ Episodio {i}: Sin URL")
                    continue
                
                # Construir la URL completa si es necesario
                if not episode_path.startswith(('http://', 'https://')):
                    episode_url = f"https://w.wallhaven.cc/full/{episode_path}"
                else:
                    episode_url = episode_path
                
                # Obtener el título del episodio
                title_elem = ep.select_one('.Title')
                episode_title = title_elem.text.strip() if title_elem else f'Episodio {i}'
                
                # Limpiar el título
                episode_title = ' '.join(episode_title.split())
                
                # Extraer el número de episodio si es posible
                ep_number = i
                num_match = re.search(r'(\d+)', episode_title)
                if num_match:
                    try:
                        ep_number = int(num_match.group(1))
                    except (ValueError, IndexError):
                        pass
                
                # Agregar el episodio a la lista
                episodes.append({
                    'number': ep_number,
                    'title': episode_title,
                    'url': episode_url
                })
                
                print(f"  - ✅ Episodio {ep_number}: {episode_title}")
                
            except Exception as ep_err:
                print(f"  - ❌ Error al procesar episodio {i}: {str(ep_err)}")
                import traceback
                print(traceback.format_exc())
        
        if not episodes:
            print("  - ❌ No se pudieron extraer episodios")
            return None
            
        print(f"  - 🎉 Se extrajeron {len(episodes)} episodios exitosamente")
        return episodes
        
    except requests.exceptions.RequestException as re:
        print(f"  - ❌ Error de conexión: {str(re)}")
    except Exception as e:
        print(f"  - ❌ Error inesperado: {str(e)}")
        import traceback
        print(traceback.format_exc())
    
    return None

def get_episodes_from_animeflv(anime):
    """
    Obtiene el número de episodios de un anime desde AnimeFLV usando el slug del anime.
    
    Args:
        anime (dict): Diccionario con la información del anime
        
    Returns:
        list: Lista con un diccionario que contiene el conteo de episodios o lista vacía en caso de error
    """
    print(f"\n=== Buscando episodios para: {anime.get('nombre', 'Desconocido')} ===")
    
    try:
        from animeflv import AnimeFLV
        
        # Crear instancia de la API
        with AnimeFLV() as api:
            # Buscar el anime
            search_results = api.search(anime.get('nombre', ''))
            
            if not search_results:
                print("❌ No se encontraron resultados para el anime")
                return []
                
            print(f"\n🔍 {len(search_results)} resultados encontrados")
            
            # Mostrar los primeros 3 resultados para depuración
            for i, result in enumerate(search_results[:3], 1):
                print(f"{i}. {result.title} (ID: {result.id})")
            
            # Buscar primero una serie de TV (evitar películas y OVAs)
            selected = None
            for result in search_results:
                title_lower = result.title.lower()
                if 'movie' not in title_lower and 'ova' not in title_lower and 'special' not in title_lower:
                    selected = result
                    break
            
            # Si no se encuentra una serie, usar el primer resultado
            if selected is None and search_results:
                selected = search_results[0]
                
            print(f"\n🎯 Seleccionado: {selected.title}")
            
            # Obtener información del anime
            info = api.get_anime_info(selected.id)
            
            if not info or not hasattr(info, 'episodes') or not info.episodes:
                print("❌ No se pudieron obtener los episodios")
                return []
            
            # Contar episodios únicos (por si hay duplicados)
            episode_count = len(set(ep.id for ep in info.episodes))
            print(f"\n📺 Total de episodios encontrados: {episode_count}")
            
            # Devolver solo la información básica del conteo de episodios
            return [{
                'episode_count': episode_count,
                'title': selected.title,
                'animeflv_id': selected.id,
                'slug': selected.id  # Usamos el ID como slug para compatibilidad
            }]
            
    except Exception as e:
        print(f"❌ Error al obtener episodios: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return []

def search_anime_in_animeflv(search_term, romanji_title=None):
    try:
        response = requests.get(f'https://animeflv.net/api/animes/search?q={search_term}')
        response.raise_for_status()
    except requests.exceptions.RequestException as re:
        print(f"  - ❌ Error de conexión: {str(re)}")
        return []

    try:
        data = json.loads(response.text)
    except json.JSONDecodeError as je:
        print(f"  - ❌ Error al decodificar JSON: {str(je)}")
        return []

    results = []
    for anime in data:
        if romanji_title and romanji_title.lower() in anime['title'].lower():
            results.insert(0, anime)
        else:
            results.append(anime)

    return results

class AnimeFLV:
    def __init__(self):
        self.base_url = 'https://www3.animeflv.net'
        self.api_url = 'https://animeflv.net/api'  # Base URL for API endpoints
        self.api_base = 'https://www3.animeflv.net'  # Base URL for direct API calls
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://animeflv.net/',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json, text/javascript, */*; q=0.01'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _extract_episode_number(self, url):
        """Extract episode number from an episode URL"""
        import re
        if not url:
            return None
            
        # Try different patterns to extract episode number
        patterns = [
            r'-(\d+)(?:-|$)',        # -23, -23-1, -23-vostfr
            r'/(\d+)(?:-|$)',         # /23, /23-1
            r'[eE]p(?:isode)?[.\s]*(\d+)',  # Ep23, ep.23, ep 23
            r'cap(?:itulo)?[.\s]*(\d+)',    # cap1, cap.1, capitulo 1
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                try:
                    return int(match.group(1))
                except (ValueError, IndexError):
                    continue
        return None
        
    def get_episode_links(self, anime_slug, episode_number=None):
        """
        Get all download links for a specific episode or all episodes
        
        Args:
            anime_slug (str): The anime slug/ID
            episode_number (int, optional): Specific episode number. If None, gets all episodes
            
        Returns:
            dict: Dictionary with episode numbers as keys and lists of download links as values
        """
        try:
            print(f"🔍 Buscando enlaces para {anime_slug} episodio {episode_number or 'todos'}")
            
            # First get the anime page to find all episodes
            anime_url = f"{self.base_url}/anime/{anime_slug}"
            response = self.session.get(anime_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Check if we got a login page
            if soup.title and 'INICIAR SESION' in soup.title.string.upper():
                print("⚠️  Página de inicio de sesión detectada. Usando método alternativo...")
                return self._get_episode_links_alternative(anime_slug, episode_number)
            
            # Find all episode links
            episode_links = {}
            for link in soup.select('a[href*="/ver/"]'):
                href = link.get('href', '')
                if anime_slug in href:
                    ep_num = self._extract_episode_number(href)
                    if ep_num is not None:
                        if episode_number is None or ep_num == episode_number:
                            if ep_num not in episode_links:
                                episode_links[ep_num] = []
                            episode_links[ep_num].append({
                                'url': f"{self.base_url}{href}" if not href.startswith('http') else href,
                                'title': link.get_text(strip=True) or f"Episodio {ep_num}"
                            })
            
            # Now get download links for each episode
            result = {}
            for ep_num, links in episode_links.items():
                result[ep_num] = []
                for link in links:
                    print(f"📥 Obteniendo enlaces para episodio {ep_num}...")
                    download_links = self._get_episode_download_links(link['url'])
                    result[ep_num].extend(download_links)
                
                print(f"✅ Encontrados {len(result[ep_num])} enlaces para el episodio {ep_num}")
            
            return result
            
        except Exception as e:
            print(f"❌ Error al obtener enlaces: {str(e)}")
            return {}
    
    def _get_episode_download_links(self, episode_url):
        """Extract download links from an episode page"""
        try:
            if not episode_url or not isinstance(episode_url, str):
                print(f"⚠️ URL de episodio inválida: {episode_url}")
                return []
                
            print(f"🔗 Obteniendo enlaces de {episode_url}")
            response = self.session.get(episode_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            if not soup:
                print("⚠️ No se pudo analizar la página del episodio")
                return []
                
            links = []
            
            # Verificar si estamos en una página de error o redirección
            if soup.find('title') and ('404' in soup.find('title').text or 'Error' in soup.find('title').text):
                print(f"⚠️ Página de error detectada: {soup.find('title').text}")
                return []
            
            # Find all download buttons
            for btn in soup.select('a.Button.Sm[href*="mega.nz"], a[href*="mega.nz"], a[href*="mediafire"], a[href*="zippyshare"], a[href*="google"], a[href*="drive.google"], a[href*="yadi.sk"], a[href*="uptobox"], a[href*="fembed"]'):
                href = btn.get('href', '')
                if not href or href.startswith('#'):
                    continue
                    
                # Get the service name from URL
                service = 'Desconocido'
                if 'mega.nz' in href:
                    service = 'Mega'
                elif 'mediafire' in href:
                    service = 'MediaFire'
                elif 'zippyshare' in href:
                    service = 'ZippyShare'
                elif 'google.com' in href or 'drive.google' in href:
                    service = 'Google Drive'
                elif 'yadi.sk' in href:
                    service = 'Yandex.Disk'
                elif 'uptobox' in href:
                    service = 'Uptobox'
                elif 'fembed' in href:
                    service = 'Fembed'
                
                # Get the link text or button text
                text = btn.get_text(strip=True)
                if not text or text == '#' or len(text) > 50:
                    text = f"Descargar desde {service}"
                
                links.append({
                    'url': href,
                    'service': service,
                    'text': text,
                    'direct': 'mega.nz' in href or 'mediafire' in href or 'zippyshare' in href
                })
            
            return links
            
        except Exception as e:
            print(f"⚠️  Error al obtener enlaces de descarga: {str(e)}")
            return []
    
    def _get_episode_links_alternative(self, anime_slug, episode_number=None):
        """Alternative method to get episode links when direct access is blocked"""
        print(f"🔍 Usando método alternativo para obtener enlaces de {anime_slug}")
        try:
            if not anime_slug:
                print("❌ Error: Falta el slug del anime")
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for the anime in search results - try multiple selectors
            selectors = [
                f'a[href*="/anime/{anime_slug}"]',
                f'a[href*="/anime/{anime_slug.replace("-", "")}"]',
                f'a[href*="/anime/{anime_slug.replace("-", " ")}"]',
                f'a[href*="/anime/{anime_slug.split("-")[0]}"]'
            ]
            
            anime_link = None
            for selector in selectors:
                anime_link = soup.select_one(selector)
                if anime_link:
                    break
            
            if not anime_link:
                print("❌ No se pudo encontrar el anime en los resultados de búsqueda")
                return {}
            
            # Get the anime page URL
            anime_url = anime_link.get('href')
            if not anime_url.startswith('http'):
                anime_url = f"{self.base_url}{anime_url}"
            
            # Now get the anime page
            response = self.session.get(anime_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all episode links
            episode_links = {}
            for link in soup.select('a[href*="/ver/"]'):
                href = link.get('href', '')
                if anime_slug in href:
                    ep_num = self._extract_episode_number(href)
                    if ep_num is not None:
                        if episode_number is None or ep_num == episode_number:
                            if ep_num not in episode_links:
                                episode_links[ep_num] = []
                            episode_links[ep_num].append({
                                'url': f"{self.base_url}{href}" if not href.startswith('http') else href,
                                'title': link.get_text(strip=True) or f"Episodio {ep_num}"
                            })
            
            # Get download links for each episode
            result = {}
            for ep_num, links in episode_links.items():
                result[ep_num] = []
                for link in links:
                    print(f"📥 Obteniendo enlaces para episodio {ep_num}...")
                    download_links = self._get_episode_download_links(link['url'])
                    result[ep_num].extend(download_links)
                
                print(f"✅ Encontrados {len(result[ep_num])} enlaces para el episodio {ep_num}")
            
            return result
            
        except Exception as e:
            print(f"❌ Error en método alternativo: {str(e)}")
            return {}

    def _get_anime_info_alternative(self, anime_slug, headers):
        """Alternative method to get anime info using different approach"""
        import re  # Ensure re is imported at the start of the method
        
        try:
            print(f"🔄 Usando método alternativo para obtener información de {anime_slug}")
            
            # Try using the browse page with search
            browse_url = f"{self.base_url}/browse?q={anime_slug}"
            response = requests.get(
                browse_url, 
                headers=headers or self.headers,
                timeout=20,
                allow_redirects=True
            )
            response.raise_for_status()
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for the anime in the search results - try multiple selectors
            selectors = [
                f'a[href*="/anime/{anime_slug}"]',
                f'a[href*="/anime/{anime_slug.replace("-", "")}"]',
                f'a[href*="/anime/{anime_slug.replace("-", " ")}"]',
                f'a[href*="/anime/{anime_slug.split("-")[0]}"]'
            ]
            
            anime_link = None
            for selector in selectors:
                anime_link = soup.select_one(selector)
                if anime_link:
                    print(f"✅ Encontrado con selector: {selector}")
                    break
                
            # Extract basic info from the search result
            title = anime_link.get('title', '').strip() or 'Sin título'
            
            episode_count = 0
            
            # Method 1: Try to find episode count in the search result item
            if anime_link:
                parent = anime_link.find_parent(['article', 'div', 'li', 'tr'])
                if parent:
                    ep_text = parent.get_text()
                    ep_matches = re.findall(r'(?:Episodios?|Caps?|Eps?)\.?\s*(\d+)', ep_text, re.IGNORECASE)
                    if ep_matches:
                        try:
                            episode_count = max(int(ep) for ep in ep_matches if ep.isdigit())
                            print(f"📺 Encontrados {episode_count} episodios en el resultado de búsqueda")
                        except (ValueError, TypeError):
                            pass
            
            # Method 2: Try to find episode links in the page
            if episode_count == 0:
                episode_urls = set()
                for ep_link in soup.select('a[href*="/ver/"]'):
                    href = ep_link.get('href', '')
                    if any(term in href.lower() for term in [anime_slug, anime_slug.replace('-', '')]):
                        ep_num = self._extract_episode_number(href)
                        if ep_num is not None:
                            episode_urls.add(ep_num)
                
                if episode_urls:
                    episode_count = max(episode_urls)
                    print(f"📺 Encontrado episodio {episode_count} en los enlaces")
            else:
                # Method 2: Check for episode list
                episodes = soup.select('ul.ListEpisodios li a, .ListEpisodios li a, .episode-list a, .episodes-list a')
                if episodes:
                    # Try to extract episode numbers from the links
                    for ep in episodes:
                        href = ep.get('href', '')
                        ep_num = self._extract_episode_number(href)
                        if ep_num is not None:
                            episode_urls.add(ep_num)
                    
                    if episode_urls:
                        episode_count = max(episode_urls)
                        print(f"📺 Método 1b: Encontrado {episode_count} episodios en la lista")
                    else:
                        episode_count = len(episodes)
                        print(f"📺 Método 1b: {episode_count} episodios contados en la lista")
            
            # Method 2: Look for episode numbers in the page
            if episode_count == 0:
                import re
                # Look for common patterns like "Episodio 1", "Capítulo 1", etc.
                episode_matches = re.findall(r'(?:Episodio|Ep\.?|Capítulo|Cap\.?|#)\s*(\d+)', 
                                          soup.get_text(), re.IGNORECASE)
                if episode_matches:
                    try:
                        episode_count = max(int(ep) for ep in episode_matches)
                        print(f"📺 Método 2: Último episodio encontrado: {episode_count}")
                    except (ValueError, TypeError):
                        pass
            
            # Method 3: Check for pagination or episode range
            if episode_count == 0:
                pagination = soup.select('.pagination a, .pager a, .page-numbers a')
                if pagination:
                    numbers = []
                    for page in pagination:
                        try:
                            num = int(page.get_text().strip())
                            numbers.append(num)
                        except (ValueError, AttributeError):
                            continue
                    if numbers:
                        episode_count = max(numbers) * 12  # Assuming 12 episodes per page as fallback
                        print(f"📺 Método 3: Estimado basado en paginación: {episode_count} episodios")
            
            # Method 4: Check for episode select dropdown
            if episode_count == 0:
                select_ep = soup.select('select[name="episode"] option')
                if select_ep and len(select_ep) > 1:
                    episode_count = len(select_ep)
                    print(f"📺 Método 4: {episode_count} episodios encontrados en el selector")
            
            if episode_count == 0:
                print("⚠️ No se pudo determinar el número de episodios")
                # As a last resort, try to get from the anime info section
                info_text = soup.get_text()
                if any(x in info_text.lower() for x in ['película', 'movie', 'film']):
                    print("ℹ️ Este parece ser una película (1 episodio)")
                    episode_count = 1
            
            # Extract metadata
            result = {
                'id': str(anime_slug),
                'slug': anime_slug,
                'title': title,
                'episode_count': episode_count,
                'url': f"{self.base_url}/anime/{anime_slug}",
                'image_url': '',
                'synopsis': ''
            }
            
            # Try to get additional metadata if we have a valid page
            if title and title.upper() != 'INICIAR SESION':
                # Get canonical URL
                canonical_link = soup.select_one('link[rel="canonical"]')
                if canonical_link and 'href' in canonical_link.attrs:
                    import re
                    slug_match = re.search(r'/anime/([^/]+)', canonical_link['href'])
                    if slug_match:
                        result['slug'] = slug_match.group(1)
                
                # Get the anime image if available
                image_elem = soup.select_one('div.AnimeCover img, img.cover, .Image img, .anime-cover img')
                if image_elem and 'src' in image_elem.attrs:
                    image_url = image_elem['src']
                    if not image_url.startswith('http'):
                        image_url = f"{self.base_url}{image_url}"
                    result['image_url'] = image_url
                
                # Get the synopsis if available
                synopsis_elem = soup.select_one('div.Description, .synopsis, .sinopsis, .description, .anime-description')
                if synopsis_elem:
                    synopsis = ' '.join(synopsis_elem.stripped_strings)
                    result['synopsis'] = synopsis[:200] + '...' if len(synopsis) > 200 else synopsis
            
            return result
            
        except requests.exceptions.RequestException as re:
            print(f"❌ Error de conexión: {str(re)}")
            # Try alternative method as fallback
            return self._get_anime_info_alternative(anime_slug, {})
        except Exception as e:
            print(f"❌ Error inesperado: {str(e)}")
            import traceback
            print(traceback.format_exc())
            # Try alternative method as fallback
            return self._get_anime_info_alternative(anime_slug, {})

def search_anime_in_animeflv(anime_title, romanji_title=None):
    """Busca un anime en AnimeFLV.
    
    Args:
        anime_title (str): Título principal del anime
        romanji_title (str, optional): Título en romanji del anime
        
    Returns:
        list: Lista de resultados de búsqueda filtrados y ordenados por relevancia
    """
    try:
        animeflv_client = animeflv.AnimeFLV()
        
        import re
        
        def clean_search_term(term):
            if not term:
                return ""
            # Limpiar el término de búsqueda
            cleaned = re.sub(r'[^\w\s]', ' ', str(term).strip())
            # Reemplazar múltiples espacios por uno solo
            cleaned = re.sub(r'\s+', ' ', cleaned)
            return cleaned.strip()
        
        # Obtener términos de búsqueda únicos
        search_terms = set()
        
        # Agregar título romaji si está disponible (con mayor prioridad)
        if romanji_title:
            cleaned_romaji = clean_search_term(romanji_title)
            if cleaned_romaji:
                search_terms.add(cleaned_romaji)
                # Agregar versión sin puntuación
                search_terms.add(cleaned_romaji.replace('.', '').replace('!', '').replace('?', ''))
        
        # Agregar título principal
        if anime_title:
            cleaned_title = clean_search_term(anime_title)
            if cleaned_title and cleaned_title not in search_terms:
                search_terms.add(cleaned_title)
                # Agregar versión sin puntuación
                search_terms.add(cleaned_title.replace('.', '').replace('!', '').replace('?', ''))
        
        print(f"\n=== Términos de búsqueda generados ===")
        print("\n".join(f"- {term}" for term in search_terms))
        print("==============================\n")
        
        # Realizar búsqueda con cada término hasta encontrar resultados
        all_results = []
        seen_ids = set()
        exclude_terms = ['ova', 'especial', 'special', 'película', 'movie', 'ona']
        
        for term in search_terms:
            if not term or len(term) < 2:  # Ignorar términos muy cortos
                continue
            try:
                print(f"Buscando en AnimeFLV: '{term}'")
                results = animeflv_client.search(term)
                if results:
                    print(f"Se encontraron {len(results)} resultados con el término: {term}")
                    
                    # Filtrar resultados para excluir OVAs y otros no deseados
                    filtered_results = []
                    for result in results:
                        # Saltar si ya vimos este ID
                        if hasattr(result, 'id') and result.id in seen_ids:
                            continue
                            
                        # Verificar si es una OVA, Especial, etc.
                        title_lower = result.title.lower()
                        if any(exclude in title_lower for exclude in exclude_terms):
                            print(f"Excluyendo (es OVA/Especial): {result.title}")
                            continue
                            
                        # Calcular puntuación de coincidencia
                        score = 0
                        
                        # Priorizar títulos que coincidan exactamente
                        if romanji_title and romanji_title.lower() in title_lower:
                            score += 50
                        if anime_title and anime_title.lower() in title_lower:
                            score += 30
                            
                        # Priorizar títulos que comienzan con el término de búsqueda
                        if title_lower.startswith(term.lower()):
                            score += 20
                            
                        # Priorizar títulos más cortos (menos probable que sean OVAs/Especiales)
                        score += max(0, 20 - len(title_lower) // 5)
                        
                        # Añadir puntuación al resultado
                        result.score = score
                        filtered_results.append(result)
                        if hasattr(result, 'id'):
                            seen_ids.add(result.id)
                    
                    if filtered_results:
                        # Ordenar por puntuación y luego por longitud del título
                        filtered_results.sort(key=lambda x: (-getattr(x, 'score', 0), len(x.title)))
                        all_results.extend(filtered_results)
                        print(f"Añadidos {len(filtered_results)} resultados filtrados para '{term}'")
                    
            except Exception as e:
                print(f"Error al buscar '{term}': {str(e)}")
        
        if not all_results:
            print("No se encontraron resultados válidos después de filtrar")
            return []
            
        # Ordenar todos los resultados por puntuación (mayor a menor)
        all_results.sort(key=lambda x: getattr(x, 'score', 0), reverse=True)
        
        # Tomar solo los 10 mejores resultados para evitar demasiadas peticiones
        top_results = all_results[:10]
        
        print(f"\n=== Resultados filtrados y ordenados (mostrando {len(top_results)}) ===")
        for i, result in enumerate(top_results, 1):
            score = getattr(result, 'score', 0)
            print(f"{i}. {result.title} (ID: {getattr(result, 'id', 'N/A')}, Score: {score})")
        print("=" * 60 + "\n")
        
        return top_results
        
    except Exception as e:
        print(f"Error inesperado en search_anime_in_animeflv: {str(e)}")
        return []

def get_anime_info(anime_id):
    """Obtiene información detallada de un anime."""
    try:
        animeflv_client = animeflv.AnimeFLV()
        return animeflv_client.get_anime_info(anime_id)
    except Exception as e:
        print(f"Error al obtener información del anime: {str(e)}")
        return None

def get_anime_episodes(anime_id):
    """Obtiene la lista de episodios de un anime."""
    try:
        animeflv_client = animeflv.AnimeFLV()
        return animeflv_client.get_episodes(anime_id)
    except Exception as e:
        print(f"Error al obtener episodios: {str(e)}")
        return []

def test_connection():
    """Prueba la conexión con la API de AnimeFLV usando un anime conocido."""
    try:
        print("Testing connection with a known anime...")
        test_anime = "shingeki no kyojin"
        search_results = search_anime_in_animeflv(test_anime)
        if search_results:
            print(f"Connection successful! Found results for {test_anime}")
            return True
        else:
            print(f"No results found even for {test_anime}, API might be down")
            return False
    except Exception as e:
        print(f"Error testing connection: {str(e)}")
        return False

@app.route('/downloads/<anime_id>/<animeflv_id>')
@app.route('/downloads/<anime_id>/<animeflv_id>/<int:episode>')
def download_anime(anime_id, animeflv_id, episode=None):
    """
    Endpoint to handle anime downloads
    Fetches download links for a specific anime episode
    using the provided animeflv_id and episode number
    """
    try:
        print(f"Fetching download links for anime_id: {anime_id}, episode: {episode}")
        
        if not episode:
            return render_template('downloads.html',
                               anime={'id': anime_id, 'title': f'Anime {anime_id}'},
                               episodes=[],
                               error="Número de episodio no especificado")
        
        # Get anime from local data first
        anime_data = next((a for a in load_anime_data() if str(a.get('id')) == str(anime_id)), None)
        
        # If not found locally, try to get info from AnimeFLV
        if not anime_data:
            print(f"Anime {anime_id} not found in local data, trying to fetch from AnimeFLV...")
            try:
                from animeflv import AnimeFLV
                api = AnimeFLV()
                anime_info = api.get_anime_info(animeflv_id)
                if anime_info and hasattr(anime_info, 'title'):
                    anime_title = anime_info.title
                else:
                    anime_title = f"Anime {animeflv_id}"
                
                print(f"Fetched anime title from AnimeFLV: {anime_title}")
                anime_data = {
                    'id': anime_id,
                    'title': anime_title,
                    'animeflv_id': animeflv_id
                }
            except Exception as e:
                print(f"Error fetching anime info from AnimeFLV: {str(e)}")
                anime_data = {
                    'id': anime_id,
                    'title': f"Anime {animeflv_id}",
                    'animeflv_id': animeflv_id
                }
        
        # Initialize the AnimeFLV client
        try:
            from animeflv import AnimeFLV
            api = AnimeFLV()
            
            print(f"Fetching download links for episode {episode}...")
            try:
                results = api.get_links(animeflv_id, str(episode))
                
                # Verificar si results es None o está vacío
                if not results:
                    print(f"No se encontraron enlaces para el episodio {episode}")
                    # Intentar con el método alternativo
                    try:
                        print("Intentando con método alternativo...")
                        from animeflv import AnimeFLV
                        api_alt = AnimeFLV()
                        info = api_alt.get_anime_info(animeflv_id)
                        if info and hasattr(info, 'episodes'):
                            for ep in info.episodes:
                                if str(ep.number) == str(episode):
                                    results = api_alt.get_links(animeflv_id, ep.id)
                                    if results:
                                        print(f"¡Encontrados {len(results)} enlaces con el método alternativo!")
                                        break
                    except Exception as alt_e:
                        print(f"Error en método alternativo: {str(alt_e)}")
                
                if not results:
                    return render_template('downloads.html',
                                       anime=anime_data,
                                       episodes=[],
                                       error=f"No se encontraron enlaces para el episodio {episode}")
                
            except Exception as e:
                print(f"Error al obtener enlaces: {str(e)}")
                return render_template('downloads.html',
                                   anime=anime_data,
                                   episodes=[],
                                   error=f"Error al obtener enlaces: {str(e)}")
            
            # Asegurarnos de que results sea una lista
            if results is None:
                results = []
            elif not isinstance(results, (list, tuple)):
                results = [results] if hasattr(results, 'url') else []
            
            # Procesar los enlaces de descarga con manejo de errores
            download_links = []
            for i, result in enumerate(results):
                try:
                    if (hasattr(result, 'url') and result.url and 
                        isinstance(result.url, str) and 
                        result.url.startswith(('http://', 'https://'))):
                        download_links.append({
                            'url': result.url,
                            'server': getattr(result, 'server', f'Servidor {i+1}'),
                            'quality': 'HD'  # Default quality
                        })
                except Exception as e:
                    print(f"Error procesando enlace {i}: {str(e)}")
                    continue
            
            print(f"Found {len(download_links)} download links for episode {episode}")
            
            # Prepare episode data for the template
            episode_data = {
                'id': str(episode),
                'number': str(episode),
                'title': f"Episodio {episode}",
                'download_links': download_links
            }
            
            return render_template('downloads.html',
                               anime=anime_data,
                               episodes=[episode_data],
                               selected_episode=str(episode))
            
        except Exception as e:
            print(f"Error getting download links: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return render_template('downloads.html', 
                               anime=anime_data, 
                               episodes=[],
                               error=f"Error al obtener enlaces de descarga: {str(e)}")
    
    except Exception as e:
        print(f"Error in download_anime: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return render_template('downloads.html', 
                           anime={'id': anime_id, 'title': f'Anime {anime_id}'}, 
                           episodes=[],
                           error=f"Error al procesar la solicitud: {str(e)}")
        abort(500, description="An error occurred while processing your request")


@app.route('/downloads')
@token_required
def downloads_page(current_user):
    """Render the main downloads page"""
    next_page = g.get('next_page', 'downloads')  # Por defecto redirige a downloads
    print(f"Redirecting to next_page: {next_page}")  # Debugging
    if next_page == 'trace':
        return redirect(url_for('trace_anime'))
    elif next_page == 'downloads':
        return redirect(url_for('downloads_page'))
    else:
        return redirect(url_for('catalogo'))  # Fallback
    return render_template('downloads.html', 
                         title="Downloads",
                         anime=None,
                         download_links={},
                         current_episode=None)

# Trace.moe API endpoints
TRACE_MOE_API = 'https://api.trace.moe/search'

def search_trace_moe(image_url=None, image_file=None):
    """
    Search for anime using trace.moe API
    
    Args:
        image_url (str, optional): URL of the image to search
        image_file (FileStorage, optional): Uploaded file object
        
    Returns:
        dict: API response with search results or error
    """
    try:
        if image_url:
            # Search by URL
            params = {'url': image_url}
            response = requests.get(TRACE_MOE_API, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        
        elif image_file and allowed_file(image_file.filename):
            # Search by file upload
            files = {'image': (image_file.filename, image_file.stream, image_file.content_type)}
            response = requests.post(TRACE_MOE_API, files=files, timeout=30)
            response.raise_for_status()
            return response.json()
            
        return {'error': 'No valid image source provided'}
        
    except requests.exceptions.RequestException as e:
        print(f"Error searching trace.moe: {str(e)}")
        return {'error': f'Failed to search trace.moe: {str(e)}'}
    except Exception as e:
        print(f"Unexpected error in search_trace_moe: {str(e)}")
        return {'error': f'An unexpected error occurred: {str(e)}'}

@app.route('/trace')
@token_required
def trace_anime(current_user):
    """Handle trace.moe search requests"""
    if request.method == 'POST':
        # Handle file upload
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                results = search_trace_moe(image_file=file)
                return jsonify(results)
        
        # Handle URL submission
        image_url = request.form.get('image_url')
        if image_url:
            results = search_trace_moe(image_url=image_url)
            return jsonify(results)
            
        return jsonify({'error': 'No valid image provided'}), 400
    
    # GET request - show the search form
    return render_template('trace.html')

if __name__ == '__main__':
    app.run(debug=True)
