document.addEventListener('DOMContentLoaded', function() {
const loginForm = document.getElementById('loginForm');
const errorMessage = document.getElementById('errorMessage');
const loginButton = document.getElementById('loginButton');
const buttonText = document.getElementById('buttonText');
const loadingIndicator = document.getElementById('loadingIndicator');

// Si el token es inválido o expiró, lo eliminamos para evitar bucles
if (!isAuthenticated()) {
removeAuthToken(); // Limpia cualquier token corrupto
}
// Siempre mostramos el login. No redirigimos automáticamente a /admin.

// Función para guardar el token en una cookie
function setAuthCookie(token, minutes) {
const d = new Date();
d.setTime(d.getTime() + (minutes*60*1000));
document.cookie = `token=${token};expires=${d.toUTCString()};path=/`;
}

// Redirección directa tras login exitoso (por defecto a /downloads)
function redirectAfterLogin() {
// Revisar si hay parámetro 'next' en la URL
const urlParams = new URLSearchParams(window.location.search);
const next = urlParams.get('next');
const validDestinations = ['/downloads', '/trace'];
if (next && validDestinations.includes(next)) {
window.location.href = next;
} else {
window.location.href = '/'; // Redirección predeterminada al catálogo
}
}

loginForm.addEventListener('submit', async function(e) {
e.preventDefault();

const username = document.getElementById('username').value.trim();
const password = document.getElementById('password').value.trim();

// Validar que solo contengan números y letras
const alphanumericRegex = /^[a-zA-Z0-9]+$/;
if (!alphanumericRegex.test(username) || !alphanumericRegex.test(password)) {
    showError('El usuario y la contraseña solo pueden contener letras y números.');
    loginButton.disabled = false;
    buttonText.textContent = 'Iniciar Sesión';
    loadingIndicator.style.display = 'none';
    return;
}


// Mostrar indicador de carga
loginButton.disabled = true;
buttonText.textContent = 'Iniciando sesión...';
loadingIndicator.style.display = 'inline-block';

try {
const response = await fetch('/api/login', {
method: 'POST',
headers: {
'Content-Type': 'application/json',
},
body: JSON.stringify({ username, password })
});

const data = await response.json();

if (response.ok) {
// Guardar el token en localStorage
storeAuthToken(data.token);
if (data.success && data.token) {
storeAuthToken(data.token);
setAuthCookie(data.token, 5); // 5 minutos (ajusta según expiración real)
// Redirección directa tras login exitoso
redirectAfterLogin();
} else {
// Mostrar mensaje de error
showError(data.message || 'Error al iniciar sesión');
}
} else {
// Mostrar mensaje de error
showError(data.message || 'Error al iniciar sesión');
}
} catch (error) {
console.error('Error:', error);
showError('Error de conexión. Inténtalo de nuevo.');
} finally {
// Restaurar el botón
loginButton.disabled = false;
buttonText.textContent = 'Iniciar Sesión';
loadingIndicator.style.display = 'none';
}
});

function showError(message) {
errorMessage.textContent = message;
errorMessage.classList.remove('d-none');

// Ocultar el mensaje después de 5 segundos
setTimeout(() => {
errorMessage.classList.add('d-none');
}, 5000);
}

// Verificar si hay un mensaje de error del servidor (para redirección desde rutas protegidas)
const urlParams = new URLSearchParams(window.location.search);
const error = urlParams.get('error');
if (error) {
showError(decodeURIComponent(error));
// Limpiar el parámetro de la URL sin recargar la página
window.history.replaceState({}, document.title, window.location.pathname);
}
});
