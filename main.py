from animeflv import AnimeFLV

with AnimeFLV() as api:
    elements = api.search(input("Escribe el nombre del anime: "))

    for i, element in enumerate(elements):
        print(f"{i} | {element.title}")

    selection = int(input("Select option: "))
    anime_id = elements[selection].id  # Usamos el ID directamente

    info = api.get_anime_info(anime_id)  # <- cambio importante
    info.episodes.reverse()

    for j, episode in enumerate(info.episodes):
        print(f"{j} | Episode -> {episode.id}")

    index_episode = int(input("Select episode: "))
    capitulo = info.episodes[index_episode].id

    results = api.get_links(anime_id, capitulo)

    for result in results:
        print(f"{result.server} -> {result.url}")
