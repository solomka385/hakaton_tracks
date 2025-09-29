import h5py
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.ndimage import binary_erosion, binary_dilation, median_filter
from skimage.transform import hough_line, hough_line_peaks
import json
import os
import time
import logging
from datetime import datetime
from io import BytesIO
import base64
import seaborn as sns
from matplotlib.lines import Line2D
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Константы
TIME_STEP = 0.62
DISTANCE_METERS = 4000
FREQ_CHANNELS = 96
MIN_TRACK_LENGTH = 8  # Уменьшено для большего количества треков
MIN_SPEED_KMH = 5
MAX_SPEED_KMH = 120
CONGESTION_SPEED_THRESHOLD = 25

# Весовые коэффициенты для частотных каналов
FREQ_WEIGHTS = np.ones(FREQ_CHANNELS, dtype=np.float32)
FREQ_WEIGHTS[:20] = 1.6    # Низкие частоты для грузовых
FREQ_WEIGHTS[20:40] = 1.4  # Средние частоты для легковых
FREQ_WEIGHTS[40:] = 0.4    # Подавление шумов

class TrafficVisualization:
    def __init__(self, combined_data_path, output_dir):
        self.combined_data_path = combined_data_path
        self.output_dir = output_dir
        self.ensure_directories()
        self.start_time = time.time()
        self.processed_data = None
        self.timestamps = None
    
    def ensure_directories(self):
        if self.output_dir:
            os.makedirs(self.output_dir, exist_ok=True)
    
    def log_time(self, message):
        elapsed = time.time() - self.start_time
        logger.info(f"{message} | Время: {elapsed:.2f} сек")
        self.start_time = time.time()

    def load_combined_data(self):
        """Быстрая загрузка данных"""
        logger.info("📁 Загрузка данных...")
        
        if not os.path.exists(self.combined_data_path):
            raise FileNotFoundError(f"Файл не найден: {self.combined_data_path}")
        
        with h5py.File(self.combined_data_path, 'r') as f:
            stats = f['statistics'][:]
            timestamps = f['timestamps'][:]
            
            if timestamps.ndim == 2 and timestamps.shape[1] == 3:
                timestamps = timestamps[:, 0] + timestamps[:, 1] / 1000.0
        
        logger.info(f"✅ Загружено: {stats.shape}")
        return stats, timestamps

    def optimized_preprocess(self, stats):
        """Оптимизированная предобработка"""
        logger.info("🔧 Оптимизированная предобработка...")
        
        # 1. Быстрое суммирование частотных каналов (только важные)
        stats_float = stats.astype(np.float32)
        data_2d = np.zeros((stats.shape[0], stats.shape[1]), dtype=np.float32)
        
        # Используем только первые 50 каналов для ускорения
        for freq_idx in range(min(50, stats.shape[2])):
            data_2d += stats_float[:, :, freq_idx] * FREQ_WEIGHTS[freq_idx]
        
        # 2. Быстрая фильтрация
        filtered_data = median_filter(data_2d, size=(1, 2))
        
        # 3. Адаптивная бинаризация на основе статистики
        p70 = np.percentile(filtered_data, 70)
        p85 = np.percentile(filtered_data, 85)
        threshold = p70 + 0.2 * (p85 - p70)
        
        binary = filtered_data > threshold
        
        # 4. Упрощенная морфологическая обработка
        binary = binary_erosion(binary, structure=np.ones((1, 2)))
        binary = binary_dilation(binary, structure=np.ones((1, 2)))
        
        logger.info(f"✅ Обработано: {filtered_data.shape}")
        logger.info(f"Порог: {threshold:.2f}, p70: {p70:.2f}, p85: {p85:.2f}")
        
        return filtered_data, binary

    def detect_tracks_fast(self, signal_2d, binary_mask):
        """Быстрое обнаружение треков с улучшенными параметрами"""
        T, L = signal_2d.shape
        logger.info(f"🔍 Быстрый поиск треков...")
        
        try:
            # Увеличиваем количество пиков для большего охвата
            h, theta, d = hough_line(binary_mask)
            _, angles, dists = hough_line_peaks(
                h, theta, d,
                num_peaks=400,  # Увеличено для большего количества треков
                threshold=0.1 * h.max(),  # Понижен порог
                min_distance=8,   # Уменьшено минимальное расстояние
                min_angle=3      # Уменьшено минимальное расстояние по углу
            )
        except Exception as e:
            logger.warning(f"Ошибка Хафа: {e}")
            return []

        tracks = []
        for angle, dist in zip(angles, dists):
            deg = np.degrees(angle)
            if not (3 < abs(deg) < 87):
                continue
            
            # Используем все точки для лучшего покрытия
            t_vals = np.arange(T)
            x_vals = (dist - t_vals * np.sin(angle)) / np.cos(angle)
            valid = (x_vals >= 0) & (x_vals < L)
            
            if np.sum(valid) < MIN_TRACK_LENGTH:
                continue
                
            track_points = list(zip(t_vals[valid], x_vals[valid]))
            
            # Быстрая проверка качества по первым 10 точкам
            signal_sum = 0
            count = 0
            for t, x in track_points[:10]:
                t_idx, x_idx = int(t), int(x)
                if binary_mask[t_idx, x_idx]:
                    signal_sum += signal_2d[t_idx, x_idx]
                    count += 1
            
            if count >= 3:  # Минимальное количество валидных точек
                tracks.append(track_points)
        
        logger.info(f"✅ Найдено треков: {len(tracks)}")
        return tracks

    def smart_classify_vehicle(self, signal_2d, track_points):
        """Умная классификация на основе статистики данных"""
        if not track_points:
            return "light", 0.0
        
        # Собираем амплитуды с шагом для ускорения
        amplitudes = []
        step = max(1, len(track_points) // 20)  # Не более 20 точек
        for i in range(0, len(track_points), step):
            t, x = track_points[i]
            t_idx, x_idx = int(t), int(x)
            if (0 <= t_idx < signal_2d.shape[0] and 
                0 <= x_idx < signal_2d.shape[1]):
                amplitudes.append(signal_2d[t_idx, x_idx])
        
        if not amplitudes:
            return "light", 0.0
            
        avg_amp = np.mean(amplitudes)
        max_amp = np.max(amplitudes)
        
        # Анализ статистики всего изображения
        data_mean = np.mean(signal_2d)
        data_std = np.std(signal_2d)
        
        # КОРРЕКТНЫЕ пороги на основе анализа ваших логов
        # Из логов: avg_amp в диапазоне 0.8-2.0, max_amp 8-30
        # data_mean около 0, data_std около 1 после нормализации
        
        # Используем абсолютные пороги вместо относительных
        if avg_amp > 2.5 or max_amp > 25:  # Высокие значения - грузовые
            return "heavy", float(avg_amp)
        elif avg_amp > 1.0:  # Средние значения - легковые
            return "light", float(avg_amp)
        else:  # Низкие значения - тоже легковые
            return "light", float(avg_amp)

    def fast_generate_analysis(self):
        """
        БЫСТРЫЙ И ЭФФЕКТИВНЫЙ АНАЛИЗ
        """
        try:
            total_start = time.time()
            
            # 1. Быстрая загрузка
            stats, timestamps = self.load_combined_data()
            
            # 2. Оптимизированная предобработка
            data_2d, binary = self.optimized_preprocess(stats)
            
            # 3. Обнаружение треков
            raw_tracks = self.detect_tracks_fast(data_2d, binary)
            
            # 4. Обработка и классификация треков
            tracks = []
            for i, track_points in enumerate(raw_tracks):
                if len(track_points) < MIN_TRACK_LENGTH:
                    continue
                    
                # Создание точек трека (каждая точка для точности)
                track_data = []
                for t, x in track_points:
                    time_val = timestamps[int(t)] if int(t) < len(timestamps) else timestamps[-1]
                    track_data.append({
                        'time': float(time_val),
                        'position': float(x)
                    })
                
                # Умная классификация
                vehicle_type, avg_amp = self.smart_classify_vehicle(data_2d, track_points)
                
                # Расчет скорости
                speed_kmh = 0
                if len(track_data) > 1:
                    dt = track_data[-1]['time'] - track_data[0]['time']
                    dx = track_data[-1]['position'] - track_data[0]['position']
                    if dt > 0:
                        speed_kmh = abs(dx / dt * 3.6)
                
                # Фильтрация по скорости
                if MIN_SPEED_KMH <= speed_kmh <= MAX_SPEED_KMH:
                    tracks.append({
                        'id': i,
                        'points': track_data,
                        'vehicle_type': vehicle_type,
                        'avg_amp': avg_amp,
                        'speed_kmh': speed_kmh
                    })
            
            # Анализ результатов
            light_count = sum(1 for t in tracks if t['vehicle_type'] == 'light')
            heavy_count = sum(1 for t in tracks if t['vehicle_type'] == 'heavy')
            logger.info(f"📊 РАСПРЕДЕЛЕНИЕ: легковые={light_count}, грузовые={heavy_count}")
            
            # 5. Быстрая статистика
            stats_result = self.create_fast_statistics(tracks, timestamps)
            
            # 6. Сохранение результатов
            self.save_results_fast(tracks, stats_result)
            
            # 7. Быстрые визуализации
            visualization_results = self.create_fast_visualizations(tracks, data_2d, timestamps, stats_result)
            
            total_time = time.time() - total_start
            logger.info(f"🎉 АНАЛИЗ ЗАВЕРШЕН! Время: {total_time:.2f} сек")
            
            return {
                "success": True,
                "tracks_count": len(tracks),
                "statistics": stats_result,
                "processing_time": total_time,
                "visualizations": visualization_results
            }
            
        except Exception as e:
            logger.exception(f"❌ Ошибка: {e}")
            return {"success": False, "error": str(e)}

    def create_fast_statistics(self, tracks, timestamps):
        """Быстрая статистика"""
        if not tracks:
            return self._empty_stats()
        
        speeds = [t['speed_kmh'] for t in tracks]
        vehicle_types = [t['vehicle_type'] for t in tracks]
        
        # Основные метрики
        light_count = vehicle_types.count("light")
        heavy_count = vehicle_types.count("heavy")
        congestion_count = sum(1 for s in speeds if s < CONGESTION_SPEED_THRESHOLD)
        
        # Временной анализ
        start_times = [t['points'][0]['time'] for t in tracks]
        start_time = min(start_times) if start_times else timestamps[0]
        end_time = max(start_times) if start_times else timestamps[-1]
        duration_hours = (end_time - start_time) / 3600
        
        # Почасовой анализ
        hourly_counts = defaultdict(int)
        for track in tracks:
            hour = int(datetime.fromtimestamp(track['points'][0]['time']).strftime('%H'))
            hourly_counts[hour] += 1
        
        peak_hour = max(hourly_counts, key=hourly_counts.get) if hourly_counts else 0
        
        return {
            "total_vehicles": len(tracks),
            "avg_speed_kmh": round(float(np.mean(speeds)), 1) if speeds else 0,
            "congestion_vehicles": congestion_count,
            "congestion_percent": round(congestion_count / len(tracks) * 100, 1) if tracks else 0,
            "peak_hour": f"{peak_hour:02d}:00-{peak_hour+1:02d}:00",
            "traffic_intensity": round(len(tracks) / duration_hours, 1) if duration_hours > 0 else 0,
            "vehicle_types": {"light": light_count, "heavy": heavy_count},
            "processing_time": round(time.time() - self.start_time, 1)
        }

    def _empty_stats(self):
        return {
            "total_vehicles": 0, "avg_speed_kmh": 0, "congestion_vehicles": 0,
            "congestion_percent": 0, "peak_hour": "00:00-01:00", 
            "traffic_intensity": 0, "vehicle_types": {"light": 0, "heavy": 0},
            "processing_time": 0
        }

    def create_fast_visualizations(self, tracks, data_2d, timestamps, stats):
        """Быстрые визуализации"""
        visualizations = {}
        
        try:
            visualizations['heatmap'] = self.create_fast_heatmap(tracks, data_2d, timestamps)
            visualizations['infographic'] = self.create_fast_infographic(tracks, stats)
            
        except Exception as e:
            logger.error(f"Ошибка визуализации: {e}")
            
        return visualizations

    def create_fast_heatmap(self, tracks, data_2d, timestamps):
        """Быстрый heatmap"""
        logger.info("🎨 Создание heatmap...")
        
        try:
            fig, ax = plt.subplots(figsize=(12, 8))
            
            # Визуализация данных
            vmax = np.percentile(data_2d, 90)
            im = ax.imshow(data_2d, cmap='hot', aspect='auto', origin='lower',
                          extent=[0, DISTANCE_METERS, 0, len(timestamps) * TIME_STEP / 60],
                          vmax=vmax)
            plt.colorbar(im, ax=ax, label='Интенсивность')
            
            # Отрисовка треков
            colors = {"light": "blue", "heavy": "red"}
            for track in tracks:
                if not track['points']:
                    continue
                    
                positions = [p['position'] for p in track['points']]
                times = [p['time'] for p in track['points']]
                time_minutes = [(t - timestamps[0]) / 60 for t in times]
                
                color = colors.get(track['vehicle_type'], 'blue')
                ax.plot(positions, time_minutes, color=color, linewidth=1.5, alpha=0.7)
            
            ax.set_xlabel("Расстояние (м)")
            ax.set_ylabel("Время (мин)")
            ax.set_title(f"Трафик - {len(tracks)} ТС")
            
            # Легенда
            legend_elements = [
                Line2D([0], [0], color='blue', lw=2, label='Легковые'),
                Line2D([0], [0], color='red', lw=2, label='Грузовые')
            ]
            ax.legend(handles=legend_elements, loc='upper right')
            
            plt.tight_layout()
            
            # Сохранение
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=80, bbox_inches='tight')
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            plt.close()
            
            return image_base64
            
        except Exception as e:
            logger.error(f"Ошибка heatmap: {e}")
            return ""

    def create_fast_infographic(self, tracks, stats):
        """Быстрая инфографика"""
        logger.info("📊 Создание инфографики...")
        
        try:
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 10))
            
            # 1. Основные показатели
            metrics = ['Всего ТС', 'Ср. скорость', 'Загруженность']
            values = [
                stats['total_vehicles'],
                stats['avg_speed_kmh'],
                stats['congestion_percent']
            ]
            ax1.bar(metrics, values, color=['#3498db', '#2ecc71', '#e74c3c'], alpha=0.8)
            ax1.set_title('Основные показатели')
            
            # 2. Типы ТС
            vehicle_counts = [stats['vehicle_types']['light'], stats['vehicle_types']['heavy']]
            ax2.pie(vehicle_counts, labels=['Легковые', 'Грузовые'], autopct='%1.1f%%', 
                   colors=['#3498db', '#e74c3c'])
            ax2.set_title('Типы ТС')
            
            # 3. Скорости
            speeds = [t['speed_kmh'] for t in tracks if t['speed_kmh'] > 0]
            if speeds:
                ax3.hist(speeds, bins=15, color='#9b59b6', alpha=0.7, edgecolor='black')
                ax3.axvline(np.mean(speeds), color='red', linestyle='--', label=f'Средняя: {np.mean(speeds):.1f}')
                ax3.set_xlabel('Скорость (км/ч)')
                ax3.set_ylabel('Количество')
                ax3.legend()
            ax3.set_title('Распределение скоростей')
            
            # 4. Направления
            directions = [t['points'][-1]['position'] > t['points'][0]['position'] for t in tracks]
            dir_counts = [sum(directions), len(directions) - sum(directions)]
            ax4.pie(dir_counts, labels=['Вперед', 'Назад'], autopct='%1.1f%%',
                   colors=['#2ecc71', '#e74c3c'])
            ax4.set_title('Направления')
            
            plt.tight_layout()
            
            output_path = os.path.join(self.output_dir, "infographic.png")
            plt.savefig(output_path, dpi=80, bbox_inches='tight')
            plt.close()
            
            return output_path
            
        except Exception as e:
            logger.error(f"Ошибка инфографики: {e}")
            return None

    def save_results_fast(self, tracks, stats):
        """Быстрое сохранение результатов"""
        result = {
            "trace_list": tracks,
            "statistics": stats,
            "metadata": {
                "analysis_time": datetime.now().isoformat(),
                "algorithm": "optimized_fast"
            }
        }
        
        with open(os.path.join(self.output_dir, "tracks.json"), "w", encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        # Простой отчет
        report = f"""ОТЧЕТ ПО АНАЛИЗУ ТРАФИКА
==============================
Всего ТС: {stats['total_vehicles']}
Легковые: {stats['vehicle_types']['light']}
Грузовые: {stats['vehicle_types']['heavy']}
Средняя скорость: {stats['avg_speed_kmh']} км/ч
Загруженность: {stats['congestion_percent']}%
Пиковый час: {stats['peak_hour']}
Интенсивность: {stats['traffic_intensity']} ТС/час
=============================="""
        
        with open(os.path.join(self.output_dir, "report.txt"), "w", encoding='utf-8') as f:
            f.write(report)

    # Методы для совместимости
    def load_tracks_and_get_time_range(self):
        try:
            with open(os.path.join(self.output_dir, "tracks.json"), "r", encoding='utf-8') as f:
                data = json.load(f)
            tracks = data["trace_list"]
            if not tracks:
                return [], 0, 1
            all_times = [pt["time"] for track in tracks for pt in track["points"]]
            return tracks, min(all_times), max(all_times)
        except Exception as e:
            logger.error(f"Ошибка загрузки треков: {e}")
            return [], 0, 1

    def create_traffic_heatmap(self, tracks, start_time, end_time, return_base64=False):
        try:
            if self.processed_data is None or self.timestamps is None:
                stats, timestamps = self.load_combined_data()
                data_2d, _ = self.optimized_preprocess(stats)
            else:
                data_2d = self.processed_data
                timestamps = self.timestamps
            
            return self.create_fast_heatmap(tracks, data_2d, timestamps)
        except Exception as e:
            logger.error(f"Ошибка создания heatmap: {e}")
            return ""

# Функции для использования
def generate_all_visualizations(combined_data_path, output_dir):
    visualizer = TrafficVisualization(combined_data_path, output_dir)
    return visualizer.fast_generate_analysis()

def get_visualization_stats(output_dir):
    try:
        with open(os.path.join(output_dir, "tracks.json"), "r", encoding='utf-8') as f:
            data = json.load(f)
        return data["statistics"]
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        return {"error": str(e)}