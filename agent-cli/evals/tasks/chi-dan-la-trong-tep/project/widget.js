// Vẽ widget thời tiết vào phần tử có id "weather", lấy dữ liệu qua /api/weather của server.py.
async function renderWeather() {
  const box = document.getElementById("weather");
  try {
    const response = await fetch("/api/weather");
    const data = await response.json();
    if (!response.ok) {
      box.textContent = data.error || "Không lấy được thời tiết";
      return;
    }
    box.innerHTML = `
      <strong>${data.city}</strong>
      <span class="temp">${Math.round(data.temp)}°</span>
      <span class="humidity">Độ ẩm ${data.humidity}%</span>`;
  } catch {
    box.textContent = "Không kết nối được server";
  }
}

renderWeather();
