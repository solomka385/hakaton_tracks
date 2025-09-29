from flask import Flask, send_from_directory, jsonify, Response, request, send_file
import os
import threading
import uuid
import time
from datetime import datetime, timedelta
from traffic_visualization import TrafficVisualization, generate_all_visualizations, get_visualization_stats
import zipfile

app = Flask(__name__, static_folder='.', static_url_path='')
sessions = {}
sessions_lock = threading.Lock()

# Фиксированные пути
COMBINED_DATA_PATH = 'data/combined_data.h5'
OUTPUT_DIR = 'results'

# Очистка старых сессий
def cleanup_sessions():
    while True:
        time.sleep(1200)
        now = datetime.now()
        with sessions_lock:
            sessions_to_remove = []
            for session_id, session_data in sessions.items():
                last_active = session_data['last_active']
                if now - last_active > timedelta(minutes=30):
                    sessions_to_remove.append(session_id)
            
            for session_id in sessions_to_remove:
                del sessions[session_id]

cleanup_thread = threading.Thread(target=cleanup_sessions, daemon=True)
cleanup_thread.start()

def get_session(session_id):
    with sessions_lock:
        return sessions.get(session_id)

def update_session(session_id, updates):
    with sessions_lock:
        if session_id in sessions:
            sessions[session_id].update(updates)
            sessions[session_id]["last_active"] = datetime.now()

def create_session(session_id):
    with sessions_lock:
        sessions[session_id] = {
            "running": False,
            "done": False,
            "error": None,
            "last_active": datetime.now()
        }

@app.route('/')
def index():
    session_id = str(uuid.uuid4())
    create_session(session_id)
    response = send_from_directory('.', 'index.html')
    response.set_cookie('session_id', session_id)
    return response

@app.route('/run-analysis', methods=['POST'])
def run_analysis():
    session_id = request.cookies.get('session_id')
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Сессия не найдена"}), 400
        
    if session["running"]:
        return jsonify({"error": "Анализ уже запущен"}), 400

    update_session(session_id, {"running": True})

    def run_analysis_task():
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            
            if not os.path.exists(COMBINED_DATA_PATH):
                update_session(session_id, {
                    "running": False,
                    "done": False,
                    "error": f"Файл данных не найден: {COMBINED_DATA_PATH}"
                })
                return
            
            result = generate_all_visualizations(COMBINED_DATA_PATH, OUTPUT_DIR)
            
            if result["success"]:
                update_session(session_id, {
                    "running": False,
                    "done": True,
                    "error": None
                })
            else:
                update_session(session_id, {
                    "running": False,
                    "done": False,
                    "error": result.get("error", "Ошибка анализа")
                })
                
        except Exception as e:
            update_session(session_id, {
                "running": False,
                "done": False,
                "error": str(e)
            })

    thread = threading.Thread(target=run_analysis_task)
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started"})

@app.route('/status')
def get_status():
    session_id = request.cookies.get('session_id')
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Сессия не найдена"}), 400
    
    update_session(session_id, {})
    return jsonify({
        "running": session["running"],
        "done": session["done"],
        "error": session["error"]
    })

@app.route('/visualizations/heatmap')
def get_heatmap():
    session_id = request.cookies.get('session_id')
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Сессия не найдена"}), 400
        
    try:
        visualizer = TrafficVisualization(COMBINED_DATA_PATH, OUTPUT_DIR)
        tracks, start_time, end_time = visualizer.load_tracks_and_get_time_range()
        
        # ИСПРАВЛЕНИЕ: Проверяем результат и возвращаем корректный ответ
        image_base64 = visualizer.create_traffic_heatmap(tracks, start_time, end_time, return_base64=True)
        
        if image_base64:
            return jsonify({"success": True, "image": f"data:image/png;base64,{image_base64}"})
        else:
            return jsonify({"success": False, "error": "Не удалось создать heatmap"})
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/visualizations/infographic')
def get_infographic():
    session_id = request.cookies.get('session_id')
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Сессия не найдена"}), 400
        
    infographic_path = f"{OUTPUT_DIR}/comprehensive_infographic.png"
    if os.path.exists(infographic_path):
        return send_file(infographic_path, mimetype='image/png')
    else:
        return jsonify({"success": False, "error": "Infographic not found"})

@app.route('/visualizations/speed-distribution')
def get_speed_distribution():
    session_id = request.cookies.get('session_id')
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Сессия не найдена"}), 400
        
    speed_path = f"{OUTPUT_DIR}/speed_distribution.png"
    if os.path.exists(speed_path):
        return send_file(speed_path, mimetype='image/png')
    else:
        return jsonify({"success": False, "error": "Speed distribution chart not found"})

@app.route('/visualizations/stats')
def get_stats():
    session_id = request.cookies.get('session_id')
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Сессия не найдена"}), 400
        
    try:
        stats = get_visualization_stats(OUTPUT_DIR)
        if stats:
            return jsonify({"success": True, "data": stats})
        else:
            return jsonify({"success": False, "error": "Failed to get statistics"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/results/<path:filename>')
def results_files(filename):
    session_id = request.cookies.get('session_id')
    session = get_session(session_id)
    if not session:
        return "Сессия не найдена", 400
        
    safe_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(safe_path):
        return "Файл не найден", 404

    mime_types = {
        '.json': 'application/json',
        '.zip': 'application/zip',
        '.txt': 'text/plain',
        '.png': 'image/png',
        '.gif': 'image/gif'
    }
    
    ext = os.path.splitext(filename)[1].lower()
    mime_type = mime_types.get(ext, 'application/octet-stream')

    headers = {
        "Content-Disposition": f"attachment; filename=\"{filename}\"",
        "Content-Type": mime_type,
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }

    with open(safe_path, 'rb') as f:
        content = f.read()
    return Response(content, mimetype=mime_type, headers=headers)

@app.route('/download-all')
def download_all():
    session_id = request.cookies.get('session_id')
    session = get_session(session_id)
    if not session:
        return "Сессия не найдена", 400
    
    if not os.path.exists(OUTPUT_DIR):
        return "Результаты не найдены", 404
    
    zip_filename = f"traffic_analysis_results.zip"
    zip_path = os.path.join(OUTPUT_DIR, zip_filename)
    
    try:
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for root, dirs, files in os.walk(OUTPUT_DIR):
                for file in files:
                    if file != zip_filename:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, OUTPUT_DIR)
                        zipf.write(file_path, arcname)
        
        return send_file(zip_path, as_attachment=True, download_name=zip_filename)
    except Exception as e:
        return jsonify({"error": f"Ошибка создания архива: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3015, debug=False, threaded=True)