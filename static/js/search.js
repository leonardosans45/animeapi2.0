document.addEventListener('DOMContentLoaded', function() {
    const searchForm = document.getElementById('searchForm');
    const searchInput = document.getElementById('searchInput');
    const searchResults = document.getElementById('searchResults');
    let searchTimeout;

    // Function to search anime using AniList API
    async function searchAnime(query) {
        if (!query || query.length < 2) {
            searchResults.classList.remove('show');
            return [];
        }

        const queryString = `
        query ($search: String) {
            Page(page: 1, perPage: 10) {
                media(search: $search, type: ANIME, sort: SEARCH_MATCH) {
                    id
                    title {
                        romaji
                        english
                    }
                    coverImage {
                        medium
                    }
                    seasonYear
                    format
                }
            }
        }`;

        const variables = {
            search: query
        };

        try {
            const response = await fetch('https://graphql.anilist.co', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                },
                body: JSON.stringify({
                    query: queryString,
                    variables: variables
                })
            });

            const result = await response.json();
            return result.data.Page.media || [];
        } catch (error) {
            console.error('Error searching anime:', error);
            return [];
        }
    }

    // Function to display search results
    function displayResults(results) {
        if (!results || results.length === 0) {
            searchResults.innerHTML = '<div class="search-result-item">No results found</div>';
            searchResults.classList.add('show');
            return;
        }

        searchResults.innerHTML = results.map(anime => {
            const title = anime.title.english || anime.title.romaji;
            const year = anime.seasonYear ? `(${anime.seasonYear})` : '';
            const type = anime.format ? `[${anime.format}]` : '';
            
            return `
                <div class="search-result-item" data-id="${anime.id}">
                    <img src="${anime.coverImage.medium || ''}" alt="${title}" onerror="this.style.display='none';">
                    <div class="title">${title}</div>
                    <div class="year">${year} ${type}</div>
                </div>
            `;
        }).join('');

        searchResults.classList.add('show');
    }

    // Handle search input with debounce
    searchInput.addEventListener('input', async (e) => {
        clearTimeout(searchTimeout);
        const query = e.target.value.trim();
        
        if (query.length < 2) {
            searchResults.classList.remove('show');
            return;
        }

        searchTimeout = setTimeout(async () => {
            const results = await searchAnime(query);
            displayResults(results);
        }, 300);
    });

    // Handle form submission
    searchForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const query = searchInput.value.trim();
        if (query) {
            window.location.href = `{{ url_for('catalogo') }}?search=${encodeURIComponent(query)}`;
        }
    });

    // Handle click on search result
    searchResults.addEventListener('click', (e) => {
        const resultItem = e.target.closest('.search-result-item');
        if (resultItem) {
            const animeId = resultItem.dataset.id;
            window.location.href = `/anime/${animeId}`;
        }
    });

    // Close search results when clicking outside
    document.addEventListener('click', (e) => {
        if (!searchForm.contains(e.target)) {
            searchResults.classList.remove('show');
        }
    });
});
