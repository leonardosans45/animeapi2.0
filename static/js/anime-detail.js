document.addEventListener('DOMContentLoaded', function() {
    // Cargar imagen de fondo con pre-carga
    const wallpaperContainer = document.getElementById('wallpaper-container');
    if (wallpaperContainer) {
        const wallpaperUrl = wallpaperContainer.getAttribute('data-wallpaper');
        if (wallpaperUrl) {
            const img = new Image();
            
            img.onload = function() {
                wallpaperContainer.style.backgroundImage = `url('${wallpaperUrl}')`;
                wallpaperContainer.style.opacity = '1';
            };
            
            img.onerror = function() {
                console.error('Error al cargar la imagen de fondo');
                wallpaperContainer.style.opacity = '1';
            };
            
            // Iniciar la carga
            img.src = wallpaperUrl;
            
            // Timeout como respaldo
            setTimeout(() => {
                if (wallpaperContainer.style.opacity !== '1') {
                    wallpaperContainer.style.opacity = '1';
                }
            }, 1000);
        } else {
            wallpaperContainer.style.opacity = '1';
        }
    }
});
