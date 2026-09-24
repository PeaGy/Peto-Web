// Tải danh sách sản phẩm từ products.json rồi vẽ ra lưới.
const formatter = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" });

function renderProducts(list) {
  const container = document.getElementById("products");
  container.innerHTML = list
    .map(
      (product) => `
      <li class="product">
        <h2>${product.name}</h2>
        <p class="price">${formatter.format(product.price)}</p>
        ${product.stock > 0 ? "" : '<p class="sold-out">Hết hàng</p>'}
      </li>`
    )
    .join("");
  document.getElementById("status").textContent = `${list.length} sản phẩm`;
}

async function start() {
  const response = await fetch("products.json");
  const data = await response.json();
  renderProducts(data.items);
}

start();
