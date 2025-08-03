document.addEventListener('DOMContentLoaded', function() {
    const uploadForm = document.getElementById('uploadForm');
    const urlForm = document.getElementById('urlForm');
    const imageFileInput = document.getElementById('imageFile');
    const imageUrlInput = document.getElementById('imageUrl');
    const imagePreview = document.getElementById('imagePreview');
    const urlImagePreview = document.getElementById('urlImagePreview');
    const loading = document.getElementById('loading');
    const resultsContainer = document.getElementById('results');
    
    // Handle file upload preview
    imageFileInput.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function(e) {
                imagePreview.src = e.target.result;
                imagePreview.style.display = 'block';
            };
            reader.readAsDataURL(file);
        }
    });
    
    // Handle URL preview
    let urlPreviewTimeout;
    imageUrlInput.addEventListener('input', function() {
        clearTimeout(urlPreviewTimeout);
        const url = this.value.trim();
        
        if (!url) {
            urlImagePreview.style.display = 'none';
            return;
        }
        
        // Add a small delay to prevent excessive requests
        urlPreviewTimeout = setTimeout(() => {
            if (isValidUrl(url)) {
                urlImagePreview.src = url;
                urlImagePreview.style.display = 'block';
                
                // Handle image load errors
                urlImagePreview.onerror = function() {
                    urlImagePreview.style.display = 'none';
                };
            }
        }, 500);
    });
    
    // Handle form submissions
    uploadForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const file = imageFileInput.files[0];
        if (file) {
            searchByFile(file);
        }
    });
    
    urlForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const url = imageUrlInput.value.trim();
        if (url && isValidUrl(url)) {
            searchByUrl(url);
        } else {
            alert('Por favor ingresa una URL de imagen válida');
        }
    });
    
    // Search functions
    async function searchByFile(file) {
        const formData = new FormData();
        formData.append('image', file);
        
        await performSearch(formData);
    }
    
    async function searchByUrl(url) {
        const formData = new FormData();
        formData.append('image_url', url);
        
        await performSearch(formData);
    }
    
    async function performSearch(formData) {
        // Show loading indicator
        loading.style.display = 'block';
        resultsContainer.innerHTML = '';
        
        try {
            const response = await fetch('/trace', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                throw new Error(`Error HTTP! estado: ${response.status}`);
            }
            
            const data = await response.json();
            displayResults(data);
        } catch (error) {
            console.error('Error:', error);
            resultsContainer.innerHTML = `
                <div class="alert alert-danger">
                    Ocurrió un error al buscar. Por favor, inténtalo de nuevo.
                    <div class="text-muted small">${error.message}</div>
                </div>
            `;
        } finally {
            loading.style.display = 'none';
        }
    }
    
    function displayResults(data) {
        resultsContainer.innerHTML = '';
        
        if (data.error) {
            resultsContainer.innerHTML = `
                <div class="alert alert-warning">
                    ${data.error}
                </div>
            `;
            return;
        }
        
        if (!data.result || data.result.length === 0) {
            resultsContainer.innerHTML = `
                <div class="alert alert-info">
                    No se encontraron coincidencias. Intenta con otra imagen.
                </div>
            `;
            return;
        }
        
        // Mostrar hasta 3 resultados principales
        const results = data.result.slice(0, 3);
        results.forEach((item, index) => {
            const template = document.getElementById('resultTemplate').content.cloneNode(true);
            const result = template.querySelector('.result-card');
            
            // Extraer información del anime
            const anilist = item.anilist || {};
            
            // Mejorar la extracción del título del anime
            let title = 'Título desconocido';
            if (anilist.title) {
                // Intentar con varios campos posibles donde podría estar el título
                title = anilist.title.english || 
                       anilist.title.romaji || 
                       anilist.title.native || 
                       anilist.title.userPreferred ||
                       (typeof anilist.title === 'string' ? anilist.title : 'Título desconocido');
            } else if (item.filename) {
                // Si no hay información de anilist, intentar extraer del nombre del archivo
                const filename = item.filename.replace(/[-_.]/g, ' ');
                title = filename.split(' ').map(word => 
                    word.charAt(0).toUpperCase() + word.slice(1)
                ).join(' ');
            }
            
            // Obtener título nativo si está disponible
            const nativeTitle = (anilist.title?.native && anilist.title.native !== title) ? anilist.title.native : '';
            const episode = item.episode || 'Desconocido';
            const similarity = (item.similarity * 100).toFixed(2);
            const anilistId = anilist.id;
            
            // Rellenar la plantilla
            result.querySelector('.anime-title').textContent = title;
            
            let episodeText = `Episodio: ${episode}`;
            if (nativeTitle) {
                episodeText += ` | ${nativeTitle}`;
            }
            result.querySelector('.episode-info').textContent = episodeText;
            
            result.querySelector('.similarity').textContent = `${similarity}%`;
            
            // Configurar enlaces
            if (anilistId) {
                // Enlace de AniList
                const anilistLink = result.querySelector('a:nth-of-type(1)');
                anilistLink.href = `https://anilist.co/anime/${anilistId}`;
                anilistLink.textContent = 'Ver en AniList';
                
                // Enlace de MyAnimeList (si está disponible)
                const malId = anilist.idMal;
                if (malId) {
                    const malLink = result.querySelector('a:nth-of-type(2)');
                    malLink.href = `https://myanimelist.net/anime/${malId}`;
                    malLink.textContent = 'Ver en MyAnimeList';
                } else {
                    result.querySelector('a:nth-of-type(2)').style.display = 'none';
                }
            } else {
                // Ocultar ambos enlaces si no hay ID de AniList
                result.querySelectorAll('a').forEach(link => link.style.display = 'none');
            }
            
            // Configurar vista previa del video
            const video = result.querySelector('video source');
            if (item.video) {
                video.src = item.video;
                video.parentElement.load();
            } else {
                video.parentElement.style.display = 'none';
            }
            
            resultsContainer.appendChild(result);
        });
        
        // Desplazarse a los resultados
        resultsContainer.scrollIntoView({ behavior: 'smooth' });
    }
    
    // Función auxiliar para validar URLs
    function isValidUrl(string) {
        try {
            new URL(string);
            return true;
        } catch (_) {
            return false;
        }
    }
});