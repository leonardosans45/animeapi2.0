// Configuración
const TOKEN_KEY = 'jwt_token';
const TOKEN_EXPIRATION_KEY = 'token_expiration';
const SESSION_TIMEOUT_MINUTES = 30; 

// Almacenar el token y su tiempo de expiración
function storeAuthToken(token) {
    try {
        // Guardar el token
        localStorage.setItem(TOKEN_KEY, token);

        // Decodificar el payload del JWT para extraer el campo exp
        const payloadBase64 = token.split('.')[1];
        const payloadJson = atob(payloadBase64.replace(/-/g, '+').replace(/_/g, '/'));
        const payload = JSON.parse(payloadJson);
        if (payload.exp) {
            // exp es un timestamp UNIX en segundos
            const expirationDate = new Date(payload.exp * 1000);
            localStorage.setItem(TOKEN_EXPIRATION_KEY, expirationDate.toISOString());
        } else {
            // Si no hay exp, usar tiempo corto por seguridad
            const fallbackDate = new Date();
            fallbackDate.setSeconds(fallbackDate.getMinutes() + 3);
            localStorage.setItem(TOKEN_EXPIRATION_KEY, fallbackDate.toISOString());
        }
        return true;
    } catch (error) {
        console.error('Error al guardar el token:', error);
        return false;
    }
}

// Obtener el token almacenado
function getAuthToken() {
    return localStorage.getItem(TOKEN_KEY);
}

// Verificar si el token ha expirado
function isTokenExpired() {
    const expiration = localStorage.getItem(TOKEN_EXPIRATION_KEY);
    if (!expiration) return true;
    
    const expirationDate = new Date(expiration);
    const now = new Date();
    return now > expirationDate;
}

// Eliminar el token (cerrar sesión)
function removeAuthToken() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(TOKEN_EXPIRATION_KEY);
}

// Verificar autenticación
function isAuthenticated() {
    const token = getAuthToken();
    return token && !isTokenExpired();
}

// Interceptor para fetch que agrega el token a las peticiones
function authFetch(url, options = {}) {
    // Configuración por defecto
    const defaultOptions = {
        headers: {}
    };
    
    // Combinar opciones
    const fetchOptions = { ...defaultOptions, ...options };
    
    // Agregar el token si existe
    const token = getAuthToken();
    if (token) {
        fetchOptions.headers['Authorization'] = `Bearer ${token}`;
    }
    
    return fetch(url, fetchOptions)
        .then(response => {
            // Si recibimos un 401 (No autorizado), redirigir al login
            if (response.status === 401) {
                handleUnauthorized();
                return Promise.reject('Sesión expirada');
            }
            return response;
        });
}

// Manejar cierre de sesión no autorizado
function handleUnauthorized() {
    // Mostrar mensaje al usuario
    showSessionExpiredMessage();
    
    // Eliminar token
    removeAuthToken();
    
    // Redirigir al login después de un breve retraso
    setTimeout(() => {
        window.location.href = '/login';
    }, 2000);
}

// Mostrar mensaje de sesión expirada
function showSessionExpiredMessage() {
    // Crear el mensaje si no existe
    let messageDiv = document.getElementById('session-expired-message');
    if (!messageDiv) {
        messageDiv = document.createElement('div');
        messageDiv.id = 'session-expired-message';
        messageDiv.style.position = 'fixed';
        messageDiv.style.top = '20px';
        messageDiv.style.right = '20px';
        messageDiv.style.padding = '15px';
        messageDiv.style.backgroundColor = '#f8d7da';
        messageDiv.style.color = '#721c24';
        messageDiv.style.borderRadius = '5px';
        messageDiv.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)';
        messageDiv.style.zIndex = '9999';
        messageDiv.style.maxWidth = '300px';
        messageDiv.textContent = 'Tu sesión ha expirado. Redirigiendo al inicio de sesión...';
        document.body.appendChild(messageDiv);
        
        // Eliminar el mensaje después de 5 segundos
        setTimeout(() => {
            messageDiv.style.transition = 'opacity 0.5s';
            messageDiv.style.opacity = '0';
            setTimeout(() => {
                messageDiv.remove();
            }, 500);
        }, 5000);
    }
}

// Verificar expiración del token periódicamente
function checkTokenExpiration() {
    if (isAuthenticated() && isTokenExpired()) {
        handleUnauthorized();
    }
}

// Inicializar la verificación periódica del token
function initTokenCheck() {
    // Verificar cada minuto
    setInterval(checkTokenExpiration, 60000);
    
    // Verificar también cuando la ventana gane el foco
    window.addEventListener('focus', checkTokenExpiration);
}

// Inicializar cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', () => {
    // Si estamos en una página protegida y no estamos autenticados, redirigir al login
    const protectedPages = ['/admin', '/trace', '/downloads'];
    if (protectedPages.some(page => window.location.pathname.startsWith(page)) && !isAuthenticated()) {
        window.location.href = '/login';
    }
    
    // Cambiar el botón JOIN por el icono de usuario si está autenticado
    const joinButton = document.querySelector('.join-btn');
    if (joinButton && isAuthenticated()) {
        const userIcon = document.createElement('button');
        userIcon.className = 'user-icon';
        userIcon.innerHTML = '<i class="fa fa-user"></i>';
        joinButton.replaceWith(userIcon);
    }
    
    // Iniciar la verificación del token
    initTokenCheck();
});
