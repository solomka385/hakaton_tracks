document.addEventListener('DOMContentLoaded', () => {
  const analyzeBtn = document.getElementById('analyzeBtn');
  const loading = document.getElementById('loading');
  const statusText = document.getElementById('statusText');
  const results = document.getElementById('results');
  const statsText = document.getElementById('statsText');
  const downloadJson = document.getElementById('downloadJson');
  const downloadReport = document.getElementById('downloadReport');
  const downloadAll = document.getElementById('downloadAll');

  // Универсальная функция скачивания через Blob
  async function forceDownload(url, filename) {
    try {
      // Скачиваем файл как Blob
      const response = await fetch(url);
      if (!response.ok) throw new Error('Ошибка загрузки файла');
      
      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);
      
      // Создаем временную ссылку для скачивания
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = filename;
      link.style.display = 'none';
      
      // Для мобильных устройств добавляем специальные атрибуты
      link.setAttribute('target', '_blank');
      link.setAttribute('rel', 'noopener noreferrer');
      
      document.body.appendChild(link);
      
      // Пытаемся вызвать скачивание
      let downloadSuccess = false;
      try {
        link.click();
        downloadSuccess = true;
      } catch (e) {
        console.error('Link click failed:', e);
      }
      
      // Если не сработало, показываем инструкцию
      setTimeout(() => {
        if (!downloadSuccess) {
          showDownloadInstruction(filename, blobUrl);
        }
        
        // Очистка
        setTimeout(() => {
          URL.revokeObjectURL(blobUrl);
          if (document.body.contains(link)) {
            document.body.removeChild(link);
          }
        }, 10000);
      }, 1000);
      
    } catch (error) {
      console.error('Download error:', error);
      showInstruction(`Ошибка скачивания: ${error.message}`);
    }
  }

  function showDownloadInstruction(filename, blobUrl) {
    const message = `
      <div style="text-align: center;">
        <h3 style="margin-bottom: 15px; color: #00d1b2;">Скачать файл</h3>
        <p style="margin-bottom: 15px;">Для скачивания файла <strong>${filename}</strong>:</p>
        <div style="display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;">
          <button onclick="handleDownload('${blobUrl}', '${filename}')" 
                  style="padding: 10px 20px; background: #7e6cff; color: white; border: none; border-radius: 8px; cursor: pointer;">
            📥 Скачать сейчас
          </button>
          <a href="${blobUrl}" download="${filename}" target="_blank"
             style="padding: 10px 20px; background: #00d1b2; color: white; text-decoration: none; border-radius: 8px;">
            🔗 Открыть ссылку
          </a>
        </div>
        <p style="margin-top: 15px; font-size: 0.9em; opacity: 0.8;">
          Нажмите "Скачать сейчас" или используйте ссылку выше
        </p>
      </div>
    `;
    showInstruction(message);
  }

  // Глобальная функция для обработки скачивания
  window.handleDownload = function(blobUrl, filename) {
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  function showInstruction(message) {
    // Создаем оверлей
    const overlay = document.createElement('div');
    overlay.className = 'instruction-overlay';
    
    // Создаем сообщение
    const msg = document.createElement('div');
    msg.className = 'instruction-message';
    msg.innerHTML = message;
    
    // Добавляем кнопку закрытия
    const closeBtn = document.createElement('button');
    closeBtn.innerHTML = '✕';
    closeBtn.style.cssText = `
      position: absolute;
      top: 10px;
      right: 10px;
      background: none;
      border: none;
      color: #e2e0e7;
      font-size: 1.2rem;
      cursor: pointer;
      padding: 5px;
      z-index: 10001;
    `;
    closeBtn.onclick = () => {
      document.body.removeChild(overlay);
      document.body.removeChild(msg);
    };
    
    msg.appendChild(closeBtn);
    
    document.body.appendChild(overlay);
    document.body.appendChild(msg);
    
    // Автоматическое закрытие через 20 секунд
    setTimeout(() => {
      if (document.body.contains(overlay)) {
        document.body.removeChild(overlay);
      }
      if (document.body.contains(msg)) {
        document.body.removeChild(msg);
      }
    }, 20000);
  }

  // Функции для управления визуализациями
  window.loadHeatmap = async function() {
    hideAllVisualizations();
    document.getElementById('heatmap-container').style.display = 'block';
    
    try {
      const response = await fetch('/visualizations/heatmap', { credentials: 'same-origin' });
      const data = await response.json();
      
      if (data.success) {
        document.getElementById('heatmap-content').innerHTML = `
          <img src="${data.image}" alt="Heatmap" style="max-width: 100%; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.3);">
        `;
      } else {
        document.getElementById('heatmap-content').innerHTML = `
          <div style="padding: 40px; text-align: center; color: #ff6b6b;">
            ❌ Ошибка загрузки heatmap: ${data.error}
          </div>
        `;
      }
    } catch (error) {
      document.getElementById('heatmap-content').innerHTML = `
        <div style="padding: 40px; text-align: center; color: #ff6b6b;">
          ❌ Ошибка: ${error.message}
        </div>
      `;
    }
  };

  window.loadInfographic = async function() {
    hideAllVisualizations();
    document.getElementById('infographic-container').style.display = 'block';
    
    try {
      const response = await fetch('/visualizations/infographic', { credentials: 'same-origin' });
      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        document.getElementById('infographic-content').innerHTML = `
          <img src="${url}" alt="Infographic" style="max-width: 100%; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.3);">
        `;
      } else {
        document.getElementById('infographic-content').innerHTML = `
          <div style="padding: 40px; text-align: center; color: #ff6b6b;">
            ❌ Ошибка загрузки инфографики
          </div>
        `;
      }
    } catch (error) {
      document.getElementById('infographic-content').innerHTML = `
        <div style="padding: 40px; text-align: center; color: #ff6b6b;">
          ❌ Ошибка: ${error.message}
        </div>
      `;
    }
  };

  window.loadSpeedDistribution = async function() {
    hideAllVisualizations();
    document.getElementById('speed-distribution-container').style.display = 'block';
    
    try {
      const response = await fetch('/visualizations/speed-distribution', { credentials: 'same-origin' });
      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        document.getElementById('speed-distribution-content').innerHTML = `
          <img src="${url}" alt="Speed Distribution" style="max-width: 100%; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.3);">
        `;
      } else {
        document.getElementById('speed-distribution-content').innerHTML = `
          <div style="padding: 40px; text-align: center; color: #ff6b6b;">
            ❌ Ошибка загрузки графика скоростей
          </div>
        `;
      }
    } catch (error) {
      document.getElementById('speed-distribution-content').innerHTML = `
        <div style="padding: 40px; text-align: center; color: #ff6b6b;">
          ❌ Ошибка: ${error.message}
        </div>
      `;
    }
  };

  window.loadStats = async function() {
    hideAllVisualizations();
    document.getElementById('stats-detailed-container').style.display = 'block';
    
    try {
      const response = await fetch('/visualizations/stats', { credentials: 'same-origin' });
      const data = await response.json();
      
      if (data.success) {
        const stats = data.data;
        document.getElementById('stats-detailed-content').innerHTML = `
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-top: 15px;">
            <div class="stat-item">
              <h4>🚗 Общее количество ТС</h4>
              <p style="font-size: 1.5rem; font-weight: bold; color: #00d1b2;">${stats.total_vehicles}</p>
            </div>
            <div class="stat-item">
              <h4>📊 Средняя скорость</h4>
              <p style="font-size: 1.5rem; font-weight: bold; color: #7e6cff;">${stats.avg_speed_kmh} км/ч</p>
            </div>
            <div class="stat-item">
              <h4>🚦 Загруженность</h4>
              <p style="font-size: 1.5rem; font-weight: bold; color: #ff6b6b;">${stats.congestion_percent}%</p>
            </div>
            <div class="stat-item">
              <h4>🕒 Пиковый час</h4>
              <p style="font-size: 1.2rem; font-weight: bold; color: #e7298a;">${stats.peak_hour}</p>
            </div>
          </div>
          
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-top: 20px;">
            <div>
              <h4>📈 Направления движения</h4>
              <div style="background: rgba(0,0,0,0.2); padding: 15px; border-radius: 8px;">
                <p>➡️ Вперед: ${stats.directions.forward} (${stats.directions.forward_percent}%)</p>
                <p>⬅️ Назад: ${stats.directions.backward} (${stats.directions.backward_percent}%)</p>
              </div>
            </div>
            <div>
              <h4>🚛 Типы транспортных средств</h4>
              <div style="background: rgba(0,0,0,0.2); padding: 15px; border-radius: 8px;">
                <p>🚗 Легковые: ${stats.vehicle_types.light}</p>
                <p>🚐 Средние: ${stats.vehicle_types.medium}</p>
                <p>🚛 Грузовые: ${stats.vehicle_types.heavy}</p>
              </div>
            </div>
          </div>

          <div style="margin-top: 20px; padding: 15px; background: rgba(0,0,0,0.2); border-radius: 8px;">
            <h4>📊 Детальная статистика треков</h4>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px;">
              <div>
                <p><strong>Макс. скорость:</strong> ${stats.speed_stats.max_speed} км/ч</p>
                <p><strong>Мин. скорость:</strong> ${stats.speed_stats.min_speed} км/ч</p>
                <p><strong>Медианная скорость:</strong> ${stats.speed_stats.median_speed} км/ч</p>
              </div>
              <div>
                <p><strong>Ср. длина трека:</strong> ${stats.length_stats.avg_length} м</p>
                <p><strong>Макс. длина:</strong> ${stats.length_stats.max_length} м</p>
                <p><strong>Мин. длина:</strong> ${stats.length_stats.min_length} м</p>
              </div>
              <div>
                <p><strong>Ср. время в пути:</strong> ${stats.duration_stats.avg_duration} сек</p>
                <p><strong>Макс. время:</strong> ${stats.duration_stats.max_duration} сек</p>
              </div>
            </div>
          </div>
        `;
      } else {
        document.getElementById('stats-detailed-content').innerHTML = `
          <div style="padding: 40px; text-align: center; color: #ff6b6b;">
            ❌ Ошибка загрузки статистики: ${data.error}
          </div>
        `;
      }
    } catch (error) {
      document.getElementById('stats-detailed-content').innerHTML = `
        <div style="padding: 40px; text-align: center; color: #ff6b6b;">
          ❌ Ошибка: ${error.message}
        </div>
      `;
    }
  };

  function hideAllVisualizations() {
    document.getElementById('heatmap-container').style.display = 'none';
    document.getElementById('infographic-container').style.display = 'none';
    document.getElementById('speed-distribution-container').style.display = 'none';
    document.getElementById('stats-detailed-container').style.display = 'none';
  }

  analyzeBtn.addEventListener('click', async () => {
    analyzeBtn.disabled = true;
    analyzeBtn.classList.add('hidden');
    loading.classList.remove('hidden');
    statusText.textContent = "Запуск анализа...";

    try {
      const res = await fetch('/run-analysis', { 
        method: 'POST',
        credentials: 'same-origin'
      });
      if (!res.ok) throw new Error("Не удалось запустить анализ");

      while (true) {
        await new Promise(r => setTimeout(r, 1500));
        const statusRes = await fetch('/status', { credentials: 'same-origin' });
        const status = await statusRes.json();
        if (status.error) throw new Error(status.error);
        if (status.done) break;
        statusText.textContent = "Анализ в процессе... Это может занять 1-3 минуты";
      }

      statusText.textContent = "Загрузка результатов...";
      setTimeout(loadResults, 600);
    } catch (error) {
      statusText.textContent = `❌ Ошибка: ${error.message}`;
      setTimeout(() => {
        loading.classList.add('hidden');
        analyzeBtn.classList.remove('hidden');
        analyzeBtn.disabled = false;
      }, 2500);
    }
  });

  async function loadResults() {
    try {
      // Загружаем текстовый отчет
      const statsRes = await fetch('/results/statistics_report.txt', { 
        credentials: 'same-origin' 
      });
      if (statsRes.ok) {
        const reportText = await statsRes.text();
        statsText.textContent = reportText;
      } else {
        statsText.textContent = "Не удалось загрузить отчет по статистике";
      }

      // Настройка кнопок скачивания
      downloadJson.onclick = (e) => {
        e.preventDefault();
        forceDownload('/results/tracks.json', 'traffic_tracks.json');
      };
      
      downloadReport.onclick = (e) => {
        e.preventDefault();
        forceDownload('/results/statistics_report.txt', 'traffic_statistics_report.txt');
      };
      
      downloadAll.onclick = (e) => {
        e.preventDefault();
        forceDownload('/download-all', 'traffic_analysis_results.zip');
      };

      // Показываем heatmap по умолчанию
      await loadHeatmap();

      results.classList.remove('hidden');
    } catch (err) {
      console.error("Ошибка загрузки результатов:", err);
      statusText.textContent = "❌ Не удалось загрузить результаты";
      setTimeout(() => {
        loading.classList.add('hidden');
        analyzeBtn.classList.remove('hidden');
        analyzeBtn.disabled = false;
      }, 2000);
    } finally {
      loading.classList.add('hidden');
    }
  }
});