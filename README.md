# SteamGridDB Artwork Downloader

Aplicación gráfica que descarga `marquee` y `thumb` desde SteamGridDB para
las colecciones `steam/`, `heroic/` y `lutris/` de EmulationStation, y
actualiza el `gamelist.xml` correspondiente.

## Instalación

```bash
pip install -r requirements.txt
```

## Uso

```bash
python main.py
```

Desde la ventana:
1. **Examinar…** para elegir la carpeta `roms/` (ya no hace falta tocar código
   ni depender de `retrobox_paths`).
2. Pega tu API key de SteamGridDB.
3. Marca los sistemas a procesar.
4. Si activas *"Elegir imágenes manualmente"*, para cada asset se abre una
   galería de miniaturas (al estilo Playnite) donde haces click en la que
   quieras usar. Si lo dejas desactivado, se coge automáticamente la de
   mejor puntuación neta (upvotes − downvotes).
5. Si hay varios juegos candidatos en SteamGridDB con un nombre ambiguo, se
   abre un diálogo para elegir cuál es.

El proceso corre en segundo plano: la ventana no se congela mientras se
buscan o descargan imágenes, y se puede **Cancelar** en cualquier momento
(se detiene tras terminar el juego en curso).

## Estructura del proyecto

```
main.py                        # arranque de la app
sgdb_artwork/
    config.py                  # constantes (sistemas soportados, tipos de asset, etc.)
    clean.py                   # normalización de nombres de fichero
    models.py                  # dataclasses (GameCandidate, ImageCandidate, ...)
    gamelist_io.py              # leer/actualizar gamelist.xml
    downloader.py               # descarga de ficheros y de previsualizaciones
    sgdb_client.py               # envoltorio sobre el paquete `steamgrid`
    interaction.py               # contrato entre lógica y GUI (Protocol)
    worker.py                    # orquestación: recorre roms/, decide qué descargar
    gui/
        folder_picker.py         # diálogo para elegir roms/
        game_picker.py            # diálogo para desambiguar juego
        image_picker.py            # galería de miniaturas estilo Playnite
        bridge.py                  # puente thread-safe worker <-> tkinter
        main_window.py              # ventana principal (formulario + log)
```

### Por qué está dividido así

- **`worker.py` no importa tkinter.** Habla con el usuario a través de la
  interfaz `UserInteraction` (`interaction.py`). Esto permite probar toda la
  lógica de negocio sin abrir ninguna ventana, y si el día de mañana se
  quisiera una interfaz web o un modo CLI, solo haría falta escribir otra
  implementación de `UserInteraction`.
- **`sgdb_client.py` aísla la librería externa `steamgrid`.** Si esa
  librería cambia de API, el impacto se limita a un fichero.
- **`gui/bridge.py` resuelve el problema de hilos.** El scraping ocurre en
  un hilo de fondo para no congelar la ventana; los diálogos modales
  (elegir juego / elegir imagen) se crean siempre en el hilo principal de
  tkinter y el resultado se devuelve al hilo de fondo mediante una cola.
- **Cada pieza de GUI es un fichero pequeño e independiente**
  (`folder_picker`, `game_picker`, `image_picker`), fácil de encontrar y
  modificar sin tocar el resto.

## Notas

- Las previsualizaciones de la galería de imágenes se descargan en el hilo
  de fondo antes de abrir el diálogo, así que abrir la galería no bloquea
  la interfaz.
- Los `-image.png` los sigue gestionando ScreenScraper, como en el script
  original; este proyecto solo toca `-marquee.png` y `-thumb.png`.
