document.addEventListener('DOMContentLoaded', function() {
    const container = document.querySelector('.container');
    const sortButtons = document.querySelectorAll('.sort-btn');
    let currentSort = 'Name';
    let currentOrder = 'asc';
    let animeList = [];

    // Get initial data from the page
    const animeElements = document.querySelectorAll('.anime_container');
    animeElements.forEach(el => {
        const paragraphs = el.querySelectorAll('p');
        const ratingText = paragraphs[0].textContent.replace('Rating:', '').trim();
        const episodesText = paragraphs[2] ? paragraphs[2].textContent.replace('Episodes:', '').trim() : '0';
        
        animeList.push({
            element: el,
            Name: el.querySelector('h2').textContent.trim(),
            Rating: ratingText === 'N/A' ? 0 : parseFloat(ratingText) || 0,
            Genre: paragraphs[1].textContent.replace('Genre:', '').trim(),
            Episodes: episodesText === 'N/A' ? 0 : parseInt(episodesText) || 0
        });
    });

    // Sorting function
    function sortAnimes(sortBy, order) {
        return [...animeList].sort((a, b) => {
            let valueA, valueB;
            
            // Get values for comparison
            if (sortBy === 'Name' || sortBy === 'Genre') {
                valueA = (a[sortBy] || '').toString().toLowerCase();
                valueB = (b[sortBy] || '').toString().toLowerCase();
            } else {
                valueA = isNaN(parseFloat(a[sortBy])) ? 0 : parseFloat(a[sortBy]);
                valueB = isNaN(parseFloat(b[sortBy])) ? 0 : parseFloat(b[sortBy]);
            }

            // Compare values
            let comparison = 0;
            if (valueA > valueB) {
                comparison = 1;
            } else if (valueA < valueB) {
                comparison = -1;
            }

            // Apply order
            return order === 'asc' ? comparison : -comparison;
        });
    }

    // Function to update the anime list
    function updateAnimeList(sortedList) {
        container.innerHTML = '';
        sortedList.forEach(anime => {
            container.appendChild(anime.element);
        });
    }

    // Add active class to the default sort button
    function setActiveButton(sortBy) {
        sortButtons.forEach(btn => {
            if (btn.dataset.sort === sortBy) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    }

    // Handle sort button clicks
    sortButtons.forEach(button => {
        button.addEventListener('click', function() {
            const sortBy = this.dataset.sort;
            let order = this.dataset.order;

            // Toggle order if clicking the same button
            if (currentSort === sortBy) {
                order = order === 'asc' ? 'desc' : 'asc';
                this.dataset.order = order;
            } else {
                // Reset other buttons
                sortButtons.forEach(btn => {
                    if (btn !== this) {
                        btn.dataset.order = btn.dataset.sort === 'Rating' ? 'desc' : 'asc';
                    }
                });
            }

            // Update current sort
            currentSort = sortBy;
            currentOrder = order;
            setActiveButton(sortBy);

            // Sort and update
            const sorted = sortAnimes(sortBy, order);
            updateAnimeList(sorted);
        });
    });

    // Initial sort by Name
    const defaultSortButton = document.querySelector('.sort-btn[data-sort="Name"]');
    if (defaultSortButton) {
        defaultSortButton.click();
    }
});
