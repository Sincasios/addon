# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# XBMC Library Tools
# ------------------------------------------------------------

import sys

import os
import threading
import time
import re

import xbmc
from core import filetools
from core import jsontools
from core import scrapertools
from core.urlparse import urlrequest
from platformcode import config, logger
from platformcode import platformtools

PY3 = sys.version_info[0] >= 3


def mark_auto_as_watched(item):
    def mark_as_watched_subThread(item):
        logger.info()
        # logger.debug("item:\n" + item.tostring('\n'))

        condicion = config.get_setting("videolibrary_watched_setting")

        time_limit = time.time() + 30
        while not platformtools.is_playing() and time.time() < time_limit:
            time.sleep(1)

        sync_with_trakt = False

        while platformtools.is_playing():
            tiempo_actual = xbmc.Player().getTime()
            totaltime = xbmc.Player().getTotalTime()

            mark_time = 0
            if condicion == 0:  # '5 minutos'
                mark_time = 300
            elif condicion == 1:  # '30%'
                mark_time = totaltime * 0.3
            elif condicion == 2:  # '50%'
                mark_time = totaltime * 0.5
            elif condicion == 3:  # '80%'
                mark_time = totaltime * 0.8
            elif condicion == 4:  # '0 seg'
                mark_time = -1

            # logger.debug(str(tiempo_actual))
            # logger.debug(str(mark_time))

            if tiempo_actual > mark_time:
                logger.debug("marcado")
                item.playcount = 1
                sync_with_trakt = True
                from modules.videolibrary import mark_content_as_watched2
                mark_content_as_watched2(item)
                break

            time.sleep(30)

        # Sincronizacion silenciosa con Trakt
        if sync_with_trakt:
            if config.get_setting("videolibrary_trakt_sync_after_watching"):
                sync_trakt_kodi()

                # logger.debug("Fin del hilo")

    # Si esta configurado para marcar como visto
    if config.get_setting("videolibrary_mark_as_watched"):
        threading.Thread(target=mark_as_watched_subThread, args=[item]).start()


def sync_trakt_addon(path_folder):
    """
       Actualiza los valores de episodios vistos si
    """
    logger.info()
    # si existe el addon hacemos la busqueda
    if xbmc.getCondVisibility('System.HasAddon("script.trakt")'):
        # importamos dependencias
        paths = ["special://home/addons/script.module.dateutil/lib/", "special://home/addons/script.module.six/lib/",
                 "special://home/addons/script.module.arrow/lib/", "special://home/addons/script.module.trakt/lib/",
                 "special://home/addons/script.trakt/"]

        for path in paths:
            sys.path.append(filetools.translatePath(path))

        # se obtiene las series vistas
        try:
            from resources.lib.traktapi import traktAPI
            traktapi = traktAPI()
        except Exception:
            return

        shows = traktapi.getShowsWatched({})
        shows = list(shows.items())

        # obtenemos el id de la serie para comparar
        _id = re.findall("\[(.*?)\]", path_folder, flags=re.DOTALL)[0]
        logger.debug("el id es %s" % _id)

        if "tt" in _id:
            type_id = "imdb"
        elif "tvdb_" in _id:
            _id = _id.strip("tvdb_")
            type_id = "tvdb"
        elif "tmdb_" in _id:
            type_id = "tmdb"
            _id = _id.strip("tmdb_")
        else:
            logger.error("No hay _id de la serie")
            return

        # obtenemos los valores de la serie
        from core.videolibrarytools import read_nfo, write_nfo
        tvshow_file = filetools.join(path_folder, "tvshow.nfo")
        head_nfo, serie = read_nfo(tvshow_file)

        # buscamos en las series de trakt
        for show in shows:
            show_aux = show[1].to_dict()

            try:
                _id_trakt = show_aux['ids'].get(type_id, None)
                # logger.debug("ID ES %s" % _id_trakt)
                if _id_trakt:
                    if _id == _id_trakt:
                        logger.debug("ENCONTRADO!! %s" % show_aux)

                        # creamos el diccionario de trakt para la serie encontrada con el valor que tiene "visto"
                        dict_trakt_show = {}

                        for idx_season, season in enumerate(show_aux['seasons']):
                            for idx_episode, episode in enumerate(show_aux['seasons'][idx_season]['episodes']):
                                sea_epi = "%sx%s" % (show_aux['seasons'][idx_season]['number'],
                                                     str(show_aux['seasons'][idx_season]['episodes'][idx_episode][
                                                             'number']).zfill(2))

                                dict_trakt_show[sea_epi] = show_aux['seasons'][idx_season]['episodes'][idx_episode][
                                    'watched']
                        logger.debug("dict_trakt_show %s " % dict_trakt_show)

                        # obtenemos las keys que son episodios
                        regex_epi = re.compile('\d+x\d+')
                        keys_episodes = [key for key in serie.library_playcounts if regex_epi.match(key)]
                        # obtenemos las keys que son temporadas
                        keys_seasons = [key for key in serie.library_playcounts if 'season ' in key]
                        # obtenemos los numeros de las keys temporadas
                        seasons = [key.strip('season ') for key in keys_seasons]

                        # marcamos los episodios vistos
                        for k in keys_episodes:
                            serie.library_playcounts[k] = dict_trakt_show.get(k, 0)

                        for season in seasons:
                            episodios_temporada = 0
                            episodios_vistos_temporada = 0

                            # obtenemos las keys de los episodios de una determinada temporada
                            keys_season_episodes = [key for key in keys_episodes if key.startswith("%sx" % season)]

                            for k in keys_season_episodes:
                                episodios_temporada += 1
                                if serie.library_playcounts[k] > 0:
                                    episodios_vistos_temporada += 1

                            # se comprueba que si todos los episodios están vistos, se marque la temporada como vista
                            if episodios_temporada == episodios_vistos_temporada:
                                serie.library_playcounts.update({"season %s" % season: 1})

                        temporada = 0
                        temporada_vista = 0

                        for k in keys_seasons:
                            temporada += 1
                            if serie.library_playcounts[k] > 0:
                                temporada_vista += 1

                        # se comprueba que si todas las temporadas están vistas, se marque la serie como vista
                        if temporada == temporada_vista:
                            serie.library_playcounts.update({serie.title: 1})

                        logger.debug("los valores nuevos %s " % serie.library_playcounts)
                        write_nfo(tvshow_file, head_nfo, serie)

                        break
                    else:
                        continue

                else:
                    logger.error("no se ha podido obtener el id, trakt tiene: %s" % show_aux['ids'])

            except Exception:
                import traceback
                logger.error(traceback.format_exc())


def sync_trakt_kodi(silent=True):
    # Para que la sincronizacion no sea silenciosa vale con silent=False
    if xbmc.getCondVisibility('System.HasAddon("script.trakt")'):
        notificacion = True
        if (not config.get_setting("videolibrary_trakt_sync_notification") and
                platformtools.is_playing()):
            notificacion = False

        xbmc.executebuiltin('RunScript(script.trakt,action=sync,silent=%s)' % silent)
        logger.info("Sincronizacion con Trakt iniciada")

        if notificacion:
            platformtools.dialog_notification(config.get_localized_string(20000),
                                              config.get_localized_string(60045),
                                              icon=0,
                                              time=2000)


def mark_content_as_watched_on_kodi(item, value=1):
    """
    marca el contenido como visto o no visto en la libreria de Kodi
    @type item: item
    @param item: elemento a marcar
    @type value: int
    @param value: >0 para visto, 0 para no visto
    """
    logger.info()

    if not config.get_setting("videolibrary_auto_sync_kodi"):
        return

    # logger.debug("item:\n" + item.tostring('\n'))
    payload_f = ''

    if item.contentType == "movie":
        movieid = 0
        payload = {"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies",
                   "params": {"properties": ["title", "playcount", "originaltitle", "file"]},
                   "id": 1}

        data = get_data(payload)
        if 'result' in data and "movies" in data['result']:

            if item.strm_path:              #Si Item es de un episodio
                filename = filetools.basename(item.strm_path)
                head, tail = filetools.split(filetools.split(item.strm_path)[0])
            else:                           #Si Item es de la Serie
                filename = filetools.basename(item.path)
                head, tail = filetools.split(filetools.split(item.path)[0])
            path = filetools.join(tail, filename)

            for d in data['result']['movies']:
                if d['file'].replace("/", "\\").endswith(path.replace("/", "\\")):
                    # logger.debug("marco la pelicula como vista")
                    movieid = d['movieid']
                    break

        if movieid != 0:
            payload_f = {"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": {
                "movieid": movieid, "playcount": value}, "id": 1}

    else:  # item.contentType != 'movie'
        episodeid = 0
        payload = {"jsonrpc": "2.0", "method": "VideoLibrary.GetEpisodes",
                   "params": {"properties": ["title", "playcount", "showtitle", "file", "tvshowid"]},
                   "id": 1}

        data = get_data(payload)
        if 'result' in data and "episodes" in data['result']:

            if item.strm_path:              #Si Item es de un episodio
                filename = filetools.basename(item.strm_path)
                head, tail = filetools.split(filetools.split(item.strm_path)[0])
            else:                           #Si Item es de la Serie
                filename = filetools.basename(item.path)
                head, tail = filetools.split(filetools.split(item.path)[0])
            path = filetools.join(tail, filename)

            for d in data['result']['episodes']:

                if d['file'].replace("/", "\\").endswith(path.replace("/", "\\")):
                    # logger.debug("marco el episodio como visto")
                    episodeid = d['episodeid']
                    break

        if episodeid != 0:
            payload_f = {"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": {
                "episodeid": episodeid, "playcount": value}, "id": 1}

    if payload_f:
        # Marcar como visto
        data = get_data(payload_f)
        # logger.debug(str(data))
        if data['result'] != 'OK':
            logger.error("ERROR al poner el contenido como visto")


def mark_season_as_watched_on_kodi(item, value=1):
    """
        marca toda la temporada como vista o no vista en la libreria de Kodi
        @type item: item
        @param item: elemento a marcar
        @type value: int
        @param value: >0 para visto, 0 para no visto
        """
    logger.info()

    if not config.get_setting("videolibrary_auto_sync_kodi"):
        return

    # logger.debug("item:\n" + item.tostring('\n'))

    # Solo podemos marcar la temporada como vista en la BBDD de Kodi si la BBDD es local,
    # en caso de compartir BBDD esta funcionalidad no funcionara
    if config.get_setting("videolibrary_xbmc_db_location"):
        return

    if value == 0:
        value = 'Null'

    request_season = ''
    if item.contentSeason:
        request_season = ' and c12= %s' % item.contentSeason

    request_episode = ''
    if item.contentSeason and item.contentEpisodeNumber:
        season_episode = '%sx%s.strm' % (str(item.contentSeason), str(item.contentEpisodeNumber).zfill(2))
        request_episode = ' and strFileName= "%s"' % season_episode
    
    if item.video_path:
        path = item.video_path
    else:
        path = item.path

    if item.contentType == 'movie':
        video_path = filetools.join(config.get_videolibrary_path(), config.get_setting("folder_movies"))
        view = 'movie'
    else:
        video_path = filetools.join(config.get_videolibrary_path(), config.get_setting("folder_tvshows"))
        view = 'episode'

    item_path1 = "%" + path.replace("\\\\", "\\").replace(video_path, "")
    if item_path1[:-1] != "\\":
        item_path1 += "\\"
    item_path2 = item_path1.replace("\\", "/")
    
    while xbmc.getCondVisibility('Library.IsScanningVideo()'):                  # Por si la DB está Scanning
        time.sleep(1)

    sql = 'update files set playCount= %s where idFile  in ' \
          '(select idfile from %s_view where (strPath like "%s" or strPath like "%s")%s%s)' % \
          (value, view, item_path1, item_path2, request_season, request_episode)

    nun_records, records = execute_sql_kodi(sql)
    
    if not nun_records:
        return
    
    # Lanzamos un scan de la Videoteca de Kodi contra un directorio vacío para forzar el refresco de los widgets de pelis y series
    payload = {
        "jsonrpc": "2.0",
        "method": "VideoLibrary.Scan",
        "id": 1,
        "params": {"directory": filetools.join(config.get_runtime_path(), 'tools')}
    }
    while xbmc.getCondVisibility('Library.IsScanningVideo()'):
        return                                                                  # Ya está actualizando
    
    try:
        get_data(payload)
        
        """
        # Recargamos el Skin para que actualice los widgets.  Dejamos un tiempo para que termine la actualización
        xbmc.executebuiltin('ReloadSkin()')
        time.sleep(1)
        """
    except Exception:
        pass


def get_videos_watched_on_kodi(item, value=1, list_videos=False):
    """
        Obtiene la lista de videos vistos o no vistos en la libreria de Kodi
        @type item: item
        @param item: elemento a obtener
        @type value: int
        @param value: >0 para visto, 0 para no visto
        @type list_videos: bool
        @param list_videos: True: devuelve la lista obtenida en la query
        @type Return: bool si list_videos=False
        @param Return: True si list_videos=False y todos tiene el estado "value".  Si list_videos=True, devuelve lista de vídeos
        """
    logger.info()

    if not config.get_setting("videolibrary_auto_sync_kodi"):
        return

    # logger.debug("item:\n" + item.tostring('\n'))

    # Solo podemos obtener los vídeos como vistos en la BBDD de Kodi si la BBDD es local,
    # en caso de compartir BBDD esta funcionalidad no funcionara
    if config.get_setting("videolibrary_xbmc_db_location"):
        return

    # request_season = ''
    # if item.contentSeason:
    #     request_season = ' and c12= %s' % item.contentSeason
    
    if item.video_path:
        path = item.video_path
    else:
        path = item.path
    
    fields = 'strFileName, playCount'
    if item.contentType == 'movie':
        # video_path = filetools.join(config.get_videolibrary_path(), config.get_setting("folder_movies"))
        view = 'movie'
        search = ' or uniqueid_value like "%s"' % item.infoLabels['tmdb_id']
    else:
        # video_path = filetools.join(config.get_videolibrary_path(), config.get_setting("folder_tvshows"))
        if item.contentType == 'tvshow':
            view = 'season'
            fields = 'season, playCount, episodes'
            search = ' or showTitle like "*%s*" or strPath like "*%s*" or strPath like "*%s*"' \
                     % (item.contentSerieName, item.contentSerieName, item.infoLabels['originaltitle'])
            search = search.replace('*', '%')
        else:
            view = 'episode'
            search = ''
    
    tvshows_path = filetools.join(config.get_videolibrary_path(), config.get_setting("folder_tvshows"))
    item_path1 = "%" + path.replace("\\\\", "\\").replace(tvshows_path, "")
    if item_path1[:-1] != "\\":
        item_path1 += "\\"
    item_path2 = item_path1.replace("\\", "/")
    item_path3 = scrapertools.find_single_match(item_path1, '\s+(\[.*?\])')
    if not item_path3:
        item_path3 = scrapertools.slugify(item_path1, strict=False, convert=['.=', '-= ', ':=', '&= ', '  = '])
    item_path3 = '%' + item_path3 + '%'

    sql = 'select %s from %s_view where (strPath like "%s" or strPath like "%s" or strPath like "%s"%s)' \
                                                             % (fields, view, item_path1, item_path2, item_path3, search)

    nun_records, records = execute_sql_kodi(sql, silent=True)

    if not nun_records:
        if list_videos:
            return {}
        else:
            return False

    records = filetools.decode(records, trans_none=0)
    if view != 'season':
        records = dict(records)
    else:
        records_out = {}
        for season, playCount, episodes in records:
            records_out[season] = [playCount, episodes]
        records = records_out
    
    if list_videos:
        return records
        
    for path, mark in list(records.items()):
        if mark != value:
            return False
    return True


def mark_content_as_watched_on_alfa(path):
    """
        marca toda la serie o película como vista o no vista en la Videoteca de Alfa basado en su estado en la Videoteca de Kodi
        @type str: path
        @param path: carpeta de contenido a marcar
    """
    logger.info()

    if not config.get_setting("videolibrary_auto_sync_kodi"):
        return

    from modules.videolibrary import check_season_playcount
    from core.videolibrarytools import read_nfo, write_nfo

    #logger.debug("path: " + path)
    
    FOLDER_MOVIES = config.get_setting("folder_movies")
    FOLDER_TVSHOWS = config.get_setting("folder_tvshows")
    VIDEOLIBRARY_PATH = config.get_videolibrary_config_path()
    if not VIDEOLIBRARY_PATH:
        return

    # Solo podemos marcar el contenido como vista en la BBDD de Kodi si la BBDD es local,
    # en caso de compartir BBDD esta funcionalidad no funcionara
    #if config.get_setting("videolibrary_xbmc_db_location"):
    #    return
    
    path2 = ''
    if "special://" in VIDEOLIBRARY_PATH:
        if FOLDER_TVSHOWS in path:
            path2 = re. sub(r'.*?%s' % FOLDER_TVSHOWS, VIDEOLIBRARY_PATH + "/" + FOLDER_TVSHOWS, path).replace("\\", "/")
        if FOLDER_MOVIES in path:
            path2 = re. sub(r'.*?%s' % FOLDER_MOVIES, VIDEOLIBRARY_PATH + "/" + FOLDER_MOVIES, path).replace("\\", "/")

    if "\\" in path:
        path = path.replace("/", "\\")
    head_nfo, item = read_nfo(path)                                     #Leo el .nfo del contenido
    if not item or not isinstance(item.library_playcounts, dict):
        logger.error('.NFO no encontrado o erroneo: ' + path)
        return

    if FOLDER_TVSHOWS in path:                                          #Compruebo si es CINE o SERIE
        contentType = "episode_view"                                    #Marco la tabla de BBDD de Kodi Video
        nfo_name = "tvshow.nfo"                                         #Construyo el nombre del .nfo
        path1 = path.replace("\\\\", "\\").replace(nfo_name, '')        #para la SQL solo necesito la carpeta
        if not path2:
            path2 = path1.replace("\\", "/")                            #Formato no Windows
        else:
            path2 = path2.replace(nfo_name, '')
        
    else:
        contentType = "movie_view"                                      #Marco la tabla de BBDD de Kodi Video
        path1 = path.replace("\\\\", "\\")                              #Formato Windows
        if not path2:
            path2 = path1.replace("\\", "/")                            #Formato no Windows
        nfo_name = scrapertools.find_single_match(path2, '\]\/(.*?)$')  #Construyo el nombre del .nfo
        path1 = path1.replace(nfo_name, '')                             #para la SQL solo necesito la carpeta
        path2 = path2.replace(nfo_name, '')                             #para la SQL solo necesito la carpeta
    path2 = filetools.remove_smb_credential(path2)                      #Si el archivo está en un servidor SMB, quitamos las credenciales
    
    #Ejecutmos la sentencia SQL
    sql = 'select strFileName, playCount from %s where (strPath like "%s" or strPath like "%s")' % (contentType, path1, path2)
    nun_records = 0
    records = None
    nun_records, records = execute_sql_kodi(sql)                        #ejecución de la SQL
    if nun_records == 0:                                                #hay error?
        logger.error("Error en la SQL: " + sql + ": 0 registros")
        return                                                          #salimos: o no está catalogado en Kodi, o hay un error en la SQL
    
    for title, playCount in records:                                    #Ahora recorremos todos los registros obtenidos
        if contentType == "episode_view":
            title_plain = title.replace('.strm', '')                    #Si es Serie, quitamos el sufijo .strm
        else:
            title_plain = scrapertools.find_single_match(item.strm_path, '.(.*?\s\[.*?\])') #si es peli, quitamos el título
        if playCount is None or playCount == 0:                         #todavía no se ha visto, lo ponemos a 0
            playCount_final = 0
        elif playCount >= 1:
            playCount_final = 1

        item.library_playcounts.update({title_plain: playCount_final})  #actualizamos el playCount del .nfo

    if item.infoLabels['mediatype'] == "tvshow":                        #Actualizamos los playCounts de temporadas y Serie
        for season in item.library_playcounts.copy():
            if "season" in season:                                      #buscamos las etiquetas "season" dentro de playCounts
                season_num = int(scrapertools.find_single_match(season, 'season (\d+)'))    #salvamos el núm, de Temporada
                item = check_season_playcount(item, season_num)    #llamamos al método que actualiza Temps. y Series

    write_nfo(path, head_nfo, item)
    
    #logger.debug(item)


def get_data(payload):
    """
    obtiene la información de la llamada JSON-RPC con la información pasada en payload
    @type payload: dict
    @param payload: data
    :return:
    """
    logger.info("payload: %s" % payload)
    # Required header for XBMC JSON-RPC calls, otherwise you'll get a 415 HTTP response code - Unsupported media type
    headers = {'content-type': 'application/json'}

    if config.get_setting("videolibrary_xbmc_db_location"):
        try:
            try:
                xbmc_port = config.get_setting("videolibrary_xbmc_db_port")
            except Exception:
                xbmc_port = 0

            xbmc_json_rpc_url = "http://" + config.get_setting("videolibrary_xbmc_db_host") + ":" + str(
                xbmc_port) + "/jsonrpc"
            req = urlrequest.Request(xbmc_json_rpc_url, data=jsontools.dump(payload), headers=headers)
            f = urlrequest.urlopen(req)
            response = f.read()
            f.close()

            logger.info("get_data: response %s" % response)
            data = jsontools.load(response)
        except Exception as ex:
            template = "An exception of type %s occured. Arguments:\n%r"
            message = template % (type(ex).__name__, ex.args)
            logger.error("error en xbmc_json_rpc_url: %s" % message)
            data = ["error"]
    else:
        try:
            data = jsontools.load(xbmc.executeJSONRPC(jsontools.dump(payload)))
        except Exception as ex:
            template = "An exception of type %s occured. Arguments:\n%r"
            message = template % (type(ex).__name__, ex.args)
            logger.error("error en xbmc.executeJSONRPC: %s" % message)
            data = ["error"]

    #logger.info("data: %s" % data)

    return data


def update(folder_content=config.get_setting("folder_tvshows"), folder=""):
    """
    Actualiza la libreria dependiendo del tipo de contenido y la ruta que se le pase.

    @type folder_content: str
    @param folder_content: tipo de contenido para actualizar, series o peliculas
    @type folder: str
    @param folder: nombre de la carpeta a escanear.
    """
    logger.info(folder)

    if not config.get_setting("videolibrary_auto_sync_kodi"):
        return

    payload = {
        "jsonrpc": "2.0",
        "method": "VideoLibrary.Scan",
        "id": 1
    }

    if folder:
        if folder == '_scan_series':
            folder = ''
        folder = filetools.encode(folder)
        videolibrarypath = config.get_videolibrary_config_path()

        if folder.endswith('/') or folder.endswith('\\'):
            folder = folder[:-1]

        update_path = None

        if videolibrarypath.startswith("special:"):
            if videolibrarypath.endswith('/'):
                videolibrarypath = videolibrarypath[:-1]
            update_path = videolibrarypath + "/" + folder_content + "/" + folder + "/"
        else:
            update_path = filetools.join(videolibrarypath, folder_content, folder, ' ').rstrip()        #Probelmas de encode en folder
            #update_path = filetools.join(videolibrarypath, folder_content, ' ').rstrip()

        if not scrapertools.find_single_match(update_path, '(^\w+:\/\/)'):
            payload["params"] = {"directory": update_path}

    while xbmc.getCondVisibility('Library.IsScanningVideo()'):
        xbmc.sleep(500)

    get_data(payload)


def clean(mostrar_dialogo=False):
    """
    limpia la libreria de elementos que no existen
    @param mostrar_dialogo: muestra el cuadro de progreso mientras se limpia la videoteca
    @type mostrar_dialogo: bool
    """
    logger.info()

    if not config.get_setting("videolibrary_auto_sync_kodi"):
        return

    payload = {"jsonrpc": "2.0", "method": "VideoLibrary.Clean", "id": 1,
               "params": {"showdialogs": mostrar_dialogo}}
    data = get_data(payload)

    if data.get('result', False) == 'OK':
        return True

    return False


def search_library_path():
    logger.info()
    
    cine = config.get_setting('folder_movies', default='CINE')
    series = config.get_setting('folder_tvshows', default='SERIES')
    cine_win = '\\%s\\' % cine
    cine_res = '/%s/' % cine
    series_win = '\\%s\\' % series
    series_res = '/%s/' % series
    
    sql = 'SELECT strPath FROM path WHERE (idParentPath IS NULL AND strContent IS NOT NULL AND (' + \
                'strPath LIKE "%library' + cine_win + '" or strPath LIKE "%library' + cine_res + \
                '" or strPath LIKE "%library' + series_win + '" or strPath LIKE "%library' + series_res + '"))'
    nun_records, records = execute_sql_kodi(sql)
    
    if nun_records >= 1:
        logger.debug(records)
        resp = filetools.join(filetools.dirname(records[0][0][:-1]), ' ').rstrip()
        if filetools.exists(resp):
            return resp
    return None


def set_content(content_type, silent=False):
    """
    Procedimiento para auto-configurar la videoteca de kodi con los valores por defecto
    @type content_type: str ('movie' o 'tvshow')
    @param content_type: tipo de contenido para configurar, series o peliculas
    """
    continuar = True
    msg_text = ""
    videolibrarypath = config.get_setting("videolibrarypath")
    metadata_name = ""

    if content_type == 'movie':
        scraper = [config.get_localized_string(70093), config.get_localized_string(70096)]
        seleccion = platformtools.dialog_select(config.get_localized_string(70094), scraper)

        # Instalar The Movie Database
        if seleccion == -1 or seleccion == 0:
            metadata_name = 'metadata.themoviedb.org'
            if not xbmc.getCondVisibility('System.HasAddon(%s)' % metadata_name):
                if not silent:
                    # Preguntar si queremos instalar metadata.themoviedb.org
                    install = platformtools.dialog_yesno(config.get_localized_string(60046))
                else:
                    install = True

                if install:
                    try:
                        # Instalar metadata.themoviedb.org
                        xbmc.executebuiltin('InstallAddon(%s)' % metadata_name, True)
                        logger.info("Instalado el Scraper de películas de TheMovieDB")
                    except Exception:
                        pass

                continuar = (install and xbmc.getCondVisibility('System.HasAddon(%s)' % metadata_name))
                if not continuar:
                    msg_text = config.get_localized_string(60047)
            if continuar:
                xbmc.executebuiltin('Addon.OpenSettings(%s)' % metadata_name, True)

        # Instalar Universal Movie Scraper
        elif seleccion == 1:
            metadata_name = 'metadata.universal'
            if continuar and not xbmc.getCondVisibility('System.HasAddon(%s)' % metadata_name):
                continuar = False
                if not silent:
                    # Preguntar si queremos instalar metadata.universal
                    install = platformtools.dialog_yesno(config.get_localized_string(70095))
                else:
                    install = True

                if install:
                    try:
                        xbmc.executebuiltin('InstallAddon(%s)' % metadata_name, True)
                        if xbmc.getCondVisibility('System.HasAddon(%s)' % metadata_name):
                            continuar = True
                    except Exception:
                        pass

                continuar = (install and continuar)
                if not continuar:
                    msg_text = config.get_localized_string(70097)
            if continuar:
                xbmc.executebuiltin('Addon.OpenSettings(%s)' % metadata_name, True)

    else:  # SERIES
        scraper = [config.get_localized_string(90001), config.get_localized_string(70098)]
        seleccion = platformtools.dialog_select(config.get_localized_string(70107), scraper)

        # Instalar The TVDB
        if seleccion == -1 or seleccion == 0:
            metadata_name = 'metadata.tvshows.themoviedb.org'
            if not xbmc.getCondVisibility('System.HasAddon(%s)' % metadata_name):
                if not silent:
                    # Preguntar si queremos instalar metadata.tvshows.themoviedb.org
                    install = platformtools.dialog_yesno(config.get_localized_string(90002))
                else:
                    install = True

                if install:
                    try:
                        # Instalar metadata.tvshows.themoviedb.org
                        xbmc.executebuiltin('InstallAddon(%s)' % metadata_name, True)
                        logger.info("Instalado el Scraper de series de The TVDB")
                    except Exception:
                        pass

                continuar = (install and xbmc.getCondVisibility('System.HasAddon(%s)' % metadata_name))
                if not continuar:
                    msg_text = config.get_localized_string(90003)
            if continuar:
                xbmc.executebuiltin('Addon.OpenSettings(%s)' % metadata_name, True)

        # Instalar The Movie Database
        elif seleccion == 1:
            metadata_name = 'metadata.tvdb.com.python' if PY3 else 'metadata.tvdb.com'
            if continuar and not xbmc.getCondVisibility('System.HasAddon(%s)' % metadata_name):
                continuar = False
                if not silent:
                    # Preguntar si queremos instalar metadata.tvdb.com
                    install = platformtools.dialog_yesno(config.get_localized_string(60048))
                else:
                    install = True

                if install:
                    try:
                        # Instalar metadata.tvdb.com
                        xbmc.executebuiltin('InstallAddon(%s)' % metadata_name, True)
                        if xbmc.getCondVisibility('System.HasAddon(%s)' % metadata_name):
                            continuar = True
                    except Exception:
                        pass

                continuar = (install and continuar)
                if not continuar:
                    msg_text = config.get_localized_string(70099)
            if continuar:
                config.set_setting('scraper_tvshows', 1, 'videolibrary')
                xbmc.executebuiltin('Addon.OpenSettings(%s)' % metadata_name, True)

    idPath = 0
    idParentPath = 0
    if continuar:
        continuar = False

        # Buscamos el idPath
        sql = 'SELECT MAX(idPath) FROM path'
        nun_records, records = execute_sql_kodi(sql)
        if nun_records == 1:
            idPath = records[0][0] + 1

        sql_videolibrarypath = videolibrarypath
        if sql_videolibrarypath.startswith("special://"):
            sql_videolibrarypath = sql_videolibrarypath.replace('/profile/', '/%/').replace('/home/userdata/', '/%/')
            sep = '/'
        elif scrapertools.find_single_match(sql_videolibrarypath, '(^\w+:\/\/)'):
            sep = '/'
        else:
            sep = os.sep

        if not sql_videolibrarypath.endswith(sep):
            sql_videolibrarypath += sep

        # Buscamos el idParentPath
        sql = 'SELECT idPath, strPath FROM path where strPath LIKE "%s"' % sql_videolibrarypath
        nun_records, records = execute_sql_kodi(sql)

        if nun_records > 0:
            idParentPath = records[0][0]
            videolibrarypath = records[0][1][:-1]
            continuar = True
        else:
            # No existe videolibrarypath en la BD: la insertamos
            sql_videolibrarypath = videolibrarypath
            if not sql_videolibrarypath.endswith(sep):
                sql_videolibrarypath += sep

            sql = 'INSERT INTO path (idPath, strPath,  scanRecursive, useFolderNames, noUpdate, exclude) VALUES ' \
                  '(%s, "%s", 0, 0, 0, 0)' % (idPath, sql_videolibrarypath)
            nun_records, records = execute_sql_kodi(sql)
            if nun_records == 1:
                continuar = True
                idParentPath = idPath
                idPath += 1
            else:
                msg_text = config.get_localized_string(70101)

    if continuar:
        continuar = False
        
        # Fijamos strScraper y strSettings
        strScraper = metadata_name
        path_settings = filetools.translatePath("special://profile/addon_data/%s/settings.xml" % strScraper)
        settings_data = filetools.read(path_settings)
        strSettings = ' '.join(settings_data.split()).replace("> <", "><")
        strSettings = strSettings.replace("\"","\'")

        # Fijamos strContent y scanRecursive
        if content_type == 'movie':
            strContent = 'movies'
            scanRecursive = 2147483647
            useFolderNames = 1
            strActualizar = "¿Desea configurar este Scraper en español como opción por defecto para películas?"
            if not videolibrarypath.endswith(sep):
                videolibrarypath += sep
            strPath = videolibrarypath + config.get_setting("folder_movies") + sep
        else:
            strContent = 'tvshows'
            scanRecursive = 0
            useFolderNames = 0
            strActualizar = "¿Desea configurar este Scraper en español como opción por defecto para series?"
            if not videolibrarypath.endswith(sep):
                videolibrarypath += sep
            strPath = videolibrarypath + config.get_setting("folder_tvshows") + sep

        logger.info("%s: %s" % (content_type, strPath))
        # Comprobamos si ya existe strPath en la BD para evitar duplicados
        sql = 'SELECT idPath FROM path where strPath="%s"' % strPath
        nun_records, records = execute_sql_kodi(sql)
        sql = ""
        if nun_records == 0:
            # Insertamos el scraper
            sql = 'INSERT INTO path (idPath, strPath, strContent, strScraper, scanRecursive, useFolderNames, ' \
                  'strSettings, noUpdate, exclude, idParentPath) VALUES (%s, "%s", "%s", "%s", %s, %s, ' \
                  '"%s", 0, 0, %s)' % (
                      idPath, strPath, strContent, strScraper, scanRecursive, useFolderNames, strSettings, idParentPath)
        else:
            if not silent:
                # Preguntar si queremos configurar themoviedb.org como opcion por defecto
                actualizar = platformtools.dialog_yesno(config.get_localized_string(70098), strActualizar)
            else:
                actualizar = True

            if actualizar:
                # Actualizamos el scraper
                idPath = records[0][0]
                sql = 'UPDATE path SET strContent="%s", strScraper="%s", scanRecursive=%s, useFolderNames=%s, strSettings="%s" ' \
                      'WHERE idPath=%s' % (strContent, strScraper, scanRecursive, useFolderNames, strSettings, idPath)

        if sql:
            nun_records, records = execute_sql_kodi(sql)
            if nun_records > 0:
                continuar = True

        if not continuar:
            msg_text = config.get_localized_string(60055)

    if not continuar:
        heading = config.get_localized_string(70102) % content_type
    elif content_type == 'SERIES' and not xbmc.getCondVisibility(
            'System.HasAddon(metadata.tvshows.themoviedb.org)'):
        heading = config.get_localized_string(70103) % content_type
        msg_text = config.get_localized_string(60058)
    else:
        heading = config.get_localized_string(70103) % content_type
        msg_text = config.get_localized_string(70104)
    platformtools.dialog_notification(heading, msg_text, icon=1, time=3000)

    logger.info("%s: %s" % (heading, msg_text))


def execute_sql_kodi(sql, silent=False, file_db=''):
    """
    Ejecuta la consulta sql contra la base de datos de kodi
    @param sql: Consulta sql valida
    @type sql: str
    @return: Numero de registros modificados o devueltos por la consulta
    @rtype nun_records: int
    @return: lista con el resultado de la consulta
    @rtype records: list of tuples
    """
    if not silent:
        logger.info()
    nun_records = 0
    records = None

    # Buscamos el archivo de la BBDD de videos segun la version de kodi
    if not file_db:
        video_db = config.get_platform(True)['video_db']
        if video_db:
            file_db = filetools.join("special://userdata/Database", video_db)

    # metodo alternativo para localizar la BBDD
    if not file_db or not filetools.exists(file_db):
        file_db = ""
        for f in filetools.listdir("special://userdata/Database"):
            path_f = filetools.join("special://userdata/Database", f)

            if filetools.isfile(path_f) and f.lower().startswith('myvideos') and f.lower().endswith('.db'):
                file_db = path_f
                break

    if file_db:
        if not silent:
            logger.info("Archivo de BD: %s" % file_db)
        conn = None
        try:
            import sqlite3
            conn = sqlite3.connect(file_db)
            cursor = conn.cursor()

            if not silent:
                logger.info("Ejecutando sql: %s" % sql)
            cursor.execute(sql)
            conn.commit()

            records = cursor.fetchall()
            if sql.lower().startswith("select"):
                nun_records = len(records)
                if nun_records == 1 and records[0][0] is None:
                    nun_records = 0
                    records = []
            else:
                nun_records = conn.total_changes

            conn.close()
            if not silent or silent == 'found':
                logger.info("Consulta ejecutada. Registros: %s" % nun_records)

        except Exception:
            logger.error("Error al ejecutar la consulta sql: " + str(sql))
            if conn:
                conn.close()

    else:
        logger.debug("Base de datos no encontrada")

    return nun_records, records


def add_sources(path):
    logger.info()
    from xml.dom import minidom

    SOURCES_PATH = filetools.translatePath("special://userdata/sources.xml")

    if os.path.exists(SOURCES_PATH):
        xmldoc = minidom.parse(SOURCES_PATH)
    else:
        # Crear documento
        xmldoc = minidom.Document()
        nodo_sources = xmldoc.createElement("sources")

        for type in ['programs', 'video', 'music', 'picture', 'files']:
            nodo_type = xmldoc.createElement(type)
            element_default = xmldoc.createElement("default")
            element_default.setAttribute("pathversion", "1")
            nodo_type.appendChild(element_default)
            nodo_sources.appendChild(nodo_type)
        xmldoc.appendChild(nodo_sources)

    # Buscamos el nodo video
    nodo_video = xmldoc.childNodes[0].getElementsByTagName("video")[0]

    # Buscamos el path dentro de los nodos_path incluidos en el nodo_video
    nodos_paths = nodo_video.getElementsByTagName("path")
    list_path = [p.firstChild.data for p in nodos_paths]
    logger.debug(list_path)
    if path in list_path:
        logger.debug("La ruta %s ya esta en sources.xml" % path)
        return
    logger.debug("La ruta %s NO esta en sources.xml" % path)

    # Si llegamos aqui es por q el path no esta en sources.xml, asi q lo incluimos
    nodo_source = xmldoc.createElement("source")

    # Nodo <name>
    nodo_name = xmldoc.createElement("name")
    sep = os.sep
    if path.startswith("special://") or scrapertools.find_single_match(path, '(^\w+:\/\/)'):
        sep = "/"
    name = path
    if path.endswith(sep):
        name = path[:-1]
    nodo_name.appendChild(xmldoc.createTextNode(name.rsplit(sep)[-1]))
    nodo_source.appendChild(nodo_name)

    # Nodo <path>
    nodo_path = xmldoc.createElement("path")
    nodo_path.setAttribute("pathversion", "1")
    nodo_path.appendChild(xmldoc.createTextNode(path))
    nodo_source.appendChild(nodo_path)

    # Nodo <allowsharing>
    nodo_allowsharing = xmldoc.createElement("allowsharing")
    nodo_allowsharing.appendChild(xmldoc.createTextNode('true'))
    nodo_source.appendChild(nodo_allowsharing)

    # Añadimos <source>  a <video>
    nodo_video.appendChild(nodo_source)

    # Guardamos los cambios
    if not PY3:
        filetools.write(SOURCES_PATH,
                    '\n'.join([x for x in xmldoc.toprettyxml().encode("utf-8").splitlines() if x.strip()]))
    else:
        filetools.write(SOURCES_PATH,
                    b'\n'.join([x for x in xmldoc.toprettyxml().encode("utf-8").splitlines() if x.strip()]), vfs=False)


def ask_set_content(flag, silent=False):
    logger.info()
    logger.debug("videolibrary_kodi_flag %s" % config.get_setting("videolibrary_kodi_flag"))
    logger.debug("videolibrary_kodi %s" % config.get_setting("videolibrary_kodi"))

    def do_config():
        logger.debug("hemos aceptado")
        config.set_setting("videolibrary_kodi", True)
        set_content("movie", silent=True)
        set_content("tvshow", silent=True)
        add_sources(config.get_setting("videolibrarypath"))
        add_sources(config.get_setting("downloadpath"))

    if not silent:
        heading = config.get_localized_string(59971)
        linea1 = config.get_localized_string(70105)
        linea2 = config.get_localized_string(70106)
        if platformtools.dialog_yesno(heading, linea1, linea2):
            do_config()
        else:
            # no hemos aceptado
            config.set_setting("videolibrary_kodi", False)

    else:
        do_config()

    config.set_setting("videolibrary_kodi_flag", flag)
