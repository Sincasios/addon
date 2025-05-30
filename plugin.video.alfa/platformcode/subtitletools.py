# -*- coding: utf-8 -*-

from __future__ import print_function
import sys

import os
import re
import string
import traceback

from unicodedata import normalize
from core import filetools
from core import httptools
from core import jsontools
from core import scrapertools
from core import urlparse
from core.item import Item

import xbmc
import xbmcgui
from platformcode import config, logger

PY3 = sys.version_info[0] >= 3

if PY3:
    allchars = str.maketrans('', '')
else:
    allchars = string.maketrans('', '')

deletechars = ',\\/:*"<>|?'

kwargs = {'set_tls': True, 'set_tls_min': True, 'retries_cloudflare': 0, 'ignore_response_code': True, 'timeout': (5, 30), 
          'canonical': {}, 'hide_infobox': True, 'follow_redirects': False}


# Extraemos el nombre de la serie, temporada y numero de capitulo ejemplo: 'fringe 1x01'
def regex_tvshow(compare, file, sub=""):
    regex_expressions = [r'[Ss]([0-9]+)[][._-]*[Ee]([0-9]+)([^\\\\/]*)$',
                         r'[\._ \-]([0-9]+)x([0-9]+)([^\\/]*)',  # foo.1x09 
                         r'[\._ \-]([0-9]+)([0-9][0-9])([\._ \-][^\\/]*)',  # foo.109
                         r'([0-9]+)([0-9][0-9])([\._ \-][^\\/]*)',
                         r'[\\\\/\\._ -]([0-9]+)([0-9][0-9])[^\\/]*',
                         r'Season ([0-9]+) - Episode ([0-9]+)[^\\/]*',
                         r'Season ([0-9]+) Episode ([0-9]+)[^\\/]*',
                         r'[\\\\/\\._ -][0]*([0-9]+)x[0]*([0-9]+)[^\\/]*',
                         r'[[Ss]([0-9]+)\]_\[[Ee]([0-9]+)([^\\/]*)',  # foo_[s01]_[e01]
                         r'[\._ \-][Ss]([0-9]+)[\.\-]?[Ee]([0-9]+)([^\\/]*)',  # foo, s01e01, foo.s01.e01, foo.s01-e01
                         r's([0-9]+)ep([0-9]+)[^\\/]*',  # foo - s01ep03, foo - s1ep03
                         r'[Ss]([0-9]+)[][ ._-]*[Ee]([0-9]+)([^\\\\/]*)$',
                         r'[\\\\/\\._ \\[\\(-]([0-9]+)x([0-9]+)([^\\\\/]*)$',
                         r'[\\\\/\\._ \\[\\(-]([0-9]+)X([0-9]+)([^\\\\/]*)$'
                         ]
    # sub_info = ""
    tvshow = 0

    for regex in regex_expressions:
        response_file = re.findall(regex, file)
        if len(response_file) > 0:
            tvshow = 1
            if not compare:
                title = re.split(regex, file)[0]
                for char in ['[', ']', '_', '(', ')', '.', '-']:
                    title = title.replace(char, ' ')
                if title.endswith(" "):
                    title = title.strip()
                return title, response_file[0][0], response_file[0][1]
            else:
                break

    if (tvshow == 1):
        for regex in regex_expressions:
            response_sub = re.findall(regex, sub)
            if len(response_sub) > 0:
                try:
                    # sub_info = "Regex Subtitle Ep: %s," % (str(response_sub[0][1]),)
                    if (int(response_sub[0][1]) == int(response_file[0][1])):
                        return True
                except Exception:
                    pass
        return False
    if compare:
        return True
    else:
        return "", "", ""

        # Obtiene el nombre de la pelicula o capitulo de la serie guardado previamente en configuraciones del plugin 
        # y luego lo busca en el directorio de subtitulos, si los encuentra los activa.


def set_Subtitle():
    logger.info()

    exts = [".srt", ".sub", ".txt", ".smi", ".ssa", ".ass"]
    subtitle_folder_path = filetools.join(config.get_data_path(), "subtitles")

    subtitle_type = config.get_setting("subtitle_type")

    if subtitle_type == "2":
        subtitle_path = config.get_setting("subtitlepath_file")
        logger.info("Con subtitulo : " + subtitle_path)
        xbmc.Player().setSubtitles(subtitle_path)
    else:
        if subtitle_type == "0":
            subtitle_path = config.get_setting("subtitlepath_folder")
            if subtitle_path == "":
                subtitle_path = subtitle_folder_path
                config.set_setting("subtitlepath_folder", subtitle_path)
        else:
            subtitle_path = config.get_setting("subtitlepath_keyboard")
            long_v = len(subtitle_path)
            if long_v > 0:
                if subtitle_path.startswith("http") or subtitle_path[long_v - 4, long_v] in exts:
                    logger.info("Con subtitulo : " + subtitle_path)
                    xbmc.Player().setSubtitles(subtitle_path)
                    return
            else:
                subtitle_path = subtitle_folder_path
                config.set_setting("subtitlepath_keyboard", subtitle_path)

        import glob

        subtitle_name = config.get_setting("subtitle_name").replace("amp;", "")
        tvshow_title, season, episode = regex_tvshow(False, subtitle_name)
        try:
            if episode != "":
                Subnames = glob.glob(filetools.join(subtitle_path, "Tvshows", tvshow_title,
                                                  "%s %sx%s" % (tvshow_title, season, episode) + "*.??.???"))
            else:
                Subnames = glob.glob(filetools.join(subtitle_path, "Movies", subtitle_name + "*.??.???"))
            for Subname in Subnames:
                if os.path.splitext(Subname)[1] in exts:
                    logger.info("Con subtitulo : " + filetools.split(Subname)[1])
                    xbmc.Player().setSubtitles((Subname))
        except Exception:
            logger.error("error al cargar subtitulos")

            # Limpia los caracteres unicode


def _normalize(title, charset='utf-8'):
    '''Removes all accents and illegal chars for titles from the String'''
    if not isinstance(title, bytes):
        title = string.translate(title, allchars, deletechars)
        try:
            title = title.encode("utf-8")
            title = normalize('NFKD', title).encode('ASCII', 'ignore')
        except UnicodeEncodeError:
            logger.error("Error de encoding")
    else:
        title = string.translate(title, allchars, deletechars)
        try:
            # iso-8859-1
            title = title.decode(charset).encode('utf-8')
            title = normalize('NFKD', title.decode('utf-8'))
            title = title.encode('ASCII', 'ignore')
        except UnicodeEncodeError:
            logger.error("Error de encoding")
    return title

    # 


def searchSubtitle(item):
    if config.get_setting("subtitle_type") == 0:
        subtitlepath = config.get_setting("subtitlepath_folder")
        if subtitlepath == "":
            subtitlepath = filetools.join(config.get_data_path(), "subtitles")
            config.set_setting("subtitlepath_folder", subtitlepath)

    elif config.get_setting("subtitle_type") == 1:
        subtitlepath = config.get_setting("subtitlepath_keyboard")
        if subtitlepath == "":
            subtitlepath = filetools.join(config.get_data_path(), "subtitles")
            config.set_setting("subtitlepathkeyboard", subtitlepath)
        elif subtitlepath.startswith("http"):
            subtitlepath = config.get_setting("subtitlepath_folder")

    else:
        subtitlepath = config.get_setting("subtitlepath_folder")
    if subtitlepath == "":
        subtitlepath = filetools.join(config.get_data_path(), "subtitles")
        config.set_setting("subtitlepath_folder", subtitlepath)
    if not filetools.exists(subtitlepath):
        try:
            filetools.mkdir(subtitlepath)
        except Exception:
            logger.error("error no se pudo crear path subtitulos")
            return

    path_movie_subt = filetools.translatePath(filetools.join(subtitlepath, "Movies"))
    if not filetools.exists(path_movie_subt):
        try:
            filetools.mkdir(path_movie_subt)
        except Exception:
            logger.error("error no se pudo crear el path Movies")
            return
    full_path_tvshow = ""
    path_tvshow_subt = filetools.translatePath(filetools.join(subtitlepath, "Tvshows"))
    if not filetools.exists(path_tvshow_subt):
        try:
            filetools.mkdir(path_tvshow_subt)
        except Exception:
            logger.error("error no pudo crear el path Tvshows")
            return
    if item.show in item.title:
        title_new = title = urlparse.unquote_plus(item.title)
    else:
        title_new = title = urlparse.unquote_plus(item.show + " - " + item.title)
    path_video_temp = filetools.translatePath(filetools.join(config.get_runtime_path(), "resources", "subtitle.mp4"))
    if not filetools.exists(path_video_temp):
        logger.error("error : no existe el video temporal de subtitulos")
        return
    # path_video_temp = filetools.translatePath(filetools.join( ,video_temp + ".mp4" ))

    title_new = _normalize(title_new)
    tvshow_title, season, episode = regex_tvshow(False, title_new)
    if episode != "":
        full_path_tvshow = filetools.translatePath(filetools.join(path_tvshow_subt, tvshow_title))
        if not filetools.exists(full_path_tvshow):
            filetools.mkdir(full_path_tvshow)  # title_new + ".mp4"
        full_path_video_new = filetools.translatePath(
            filetools.join(full_path_tvshow, "%s %sx%s.mp4" % (tvshow_title, season, episode)))
        logger.info(full_path_video_new)
        listitem = xbmcgui.ListItem(title_new, iconImage="DefaultVideo.png", thumbnailImage="")
        listitem.setInfo("video",
                         {"Title": title_new, "Genre": "Tv shows", "episode": int(episode), "season": int(season),
                          "tvshowtitle": tvshow_title})

    else:
        full_path_video_new = filetools.translatePath(filetools.join(path_movie_subt, title_new + ".mp4"))
        listitem = xbmcgui.ListItem(title, iconImage="DefaultVideo.png", thumbnailImage="")
        listitem.setInfo("video", {"Title": title_new, "Genre": "Movies"})

    import time

    try:
        filetools.copy(path_video_temp, full_path_video_new)
        copy = True
        logger.info("nuevo path =" + full_path_video_new)
        time.sleep(2)
        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        playlist.clear()
        playlist.add(full_path_video_new, listitem)
        # xbmcPlayer = xbmc.Player(  xbmc.PLAYER_CORE_AUTO )
        xbmcPlayer = xbmc.Player()
        xbmcPlayer.play(playlist)

        # xbmctools.launchplayer(full_path_video_new,listitem)
    except Exception:
        copy = False
        logger.error("Error : no se pudo copiar")

    time.sleep(1)

    if copy:
        if xbmc.Player().isPlayingVideo():
            xbmc.executebuiltin("RunScript(script.xbmc.subtitles)")
            while xbmc.Player().isPlayingVideo():
                continue

        time.sleep(1)
        filetools.remove(full_path_video_new)
        try:
            if full_path_tvshow != "":
                filetools.rmdir(full_path_tvshow)
        except OSError:
            pass


def saveSubtitleName(item):
    if item.show in item.title:
        title = item.title
    else:
        title = item.show + " - " + item.title
    try:
        title = _normalize(title)
    except Exception:
        pass

    tvshow_title, season, episode = regex_tvshow(False, title)
    if episode != "":
        # title = "% %sx%s" %(tvshow_title,season,episode)
        config.set_setting("subtitle_name", title)
    else:
        config.set_setting("subtitle_name", title)
    return


def get_from_subdivx(sub_url, sub_data=None, sub_dir='', item=Item(), sub_url_alt=''):

    """
    :param sub_url: Url de descarga del subtitulo alojado en suvdivx.com
           Por Ejemplo: http://www.subdivx.com/bajar.php?id=573942&u=8

    :return: La ruta al subtitulo descomprimido
    """

    logger.info()

    kwargS = kwargs.copy()
    kwargS.update({'headers': {'Accept-Charset': None, 'Referer': sub_url}, 'follow_redirects': True})

    sub = ''
    sub_data = ''
    sub_url = sub_url.replace("&amp;", "&")
    if not sub_url_alt:
        sub_url_alt = httptools.obtain_domain(sub_url, scheme=True).rstrip('/') + '/descargar.php?id='
        sub_url_alt += scrapertools.find_single_match(sub_url, r'\/(\d+)$')
    if not sub_dir:
        sub_dir = filetools.join(config.get_videolibrary_path(), "subtitles")
        filetools.mkdir(sub_dir)

    if not sub_data:
        sub_data = httptools.downloadpage(sub_url_alt, **kwargS)
        location = sub_data.url or sub_data.headers.get('location', '')
        if not sub_data.proxy__ and location and sub_url_alt != location:
            sub_url = sub_data.headers['location'] = location
            ext = scrapertools.find_single_match(sub_url_alt, r'\=(\d+)$')
        else:
            sub_data = httptools.downloadpage(sub_url, **kwargS)
            sub_url = '%s' % sub_data.headers.get('location', '')
            ext = sub_url[-4::]

    if 'x-frame-options' not in sub_data.headers and sub_data.headers.get('location'):
        file_id = "subtitle_%s.zip" % ext
        filename = os.path.join(sub_dir, file_id)
        try:
            data_dl = httptools.downloadpage(sub_url, **kwargS).data
            filetools.write(filename, data_dl)
            sub = extract_file_online(sub_dir, filename)
            if sub and filetools.exists(filename):
                filetools.remove(filename)
        except Exception:
           logger.info('sub no valido')
    else:
       logger.info('sub no valido')

    return sub


def get_from_subscene(sub_url, sub_data=None, sub_dir='', item=Item()):
    import time

    """
    :param sub_url: Url de descarga del subtitulo alojado en suvdivx.com
           Por Ejemplo: https://subscene.com/subtitles/kisi-ka-bhai-kisi-ki-jaan

    :return: La ruta al subtitulo descomprimido
    """

    try:
        sub = False
        host = httptools.obtain_domain(sub_url, scheme=True)
        if not sub_dir:
            sub_dir = filetools.join(config.get_videolibrary_path(), "subtitles")
        # sub_dir_init = sub_dir
        sub_dir = filetools.join(sub_dir, sub_url.split('/')[-1])
        filetools.mkdir(sub_dir)

        if not sub_data:
            sub_data = httptools.downloadpage(sub_url, soup=True, **kwargs)
        if sub_data.sucess:
            languages = sub_data.soup.find_all('td', class_="language-start", id=re.compile('(?i)english|spanish'))

            spanish = False
            for language in languages:
                lang = language.get('id', '')
                if 'spanish' in lang:
                    spanish = True
                elem = language.find_all_next('td', class_="a1")
                
                try:
                    for subtitle in elem:
                        if lang.lower() in subtitle.a.get('href', ''):
                            sub_sub_url = urlparse.urljoin(host, subtitle.a.get('href', ''))
                            sub_name = '%s-%s' % (sub_url.split('/')[-1], lang)
                        else:
                            break
                        if item.contentType != 'episode':
                            break

                        sub_title = subtitle.a.find('span', class_=False).get_text(strip=True)
                        if item.contentEpisodeNumber:
                            pattern = r'(?i)se?(\d{2})x?ep?(\d{2})'
                        else:
                            pattern = r'(?i)se?(\d{2})'
                        if scrapertools.find_single_match(sub_title, pattern):
                            if item.contentEpisodeNumber:
                                season, episode = scrapertools.find_single_match(sub_title, pattern)
                                if int(season) != item.contentSeason or int(episode) != item.contentEpisodeNumber:
                                    continue
                            else:
                                season = scrapertools.find_single_match(sub_title, pattern)
                                if int(season) != item.contentSeason:
                                    continue
                            break

                    if not sub_sub_url:
                        continue
                    data_dl = httptools.downloadpage(sub_sub_url, soup=True, **kwargs)

                    if data_dl.sucess:
                        zip_url = urlparse.urljoin(host, data_dl.soup.find('li', class_="clearfix")\
                                                                   .find('div', class_="download")\
                                                                   .find('a').get('href', ''))
                    
                        if zip_url:
                            file_id = "%s.zip" % sub_name
                            filename = os.path.join(sub_dir, file_id)
                            if filetools.exists(filename):
                                filetools.remove(filename, silent=True)

                            data_dl = httptools.downloadpage(zip_url, **kwargs)
                            if data_dl.sucess:
                                filetools.write(filename, data_dl.data)

                                try:
                                    from core import ziptools
                                    unzipper = ziptools.ziptools()
                                    unzipper.extract(filename, sub_dir)
                                except Exception:
                                    xbmc.executebuiltin('Extract("%s", "%s")' % (filename, sub_dir))
                                time.sleep(1)
                                filetools.remove(filename, silent=True)
                                sub = True

                except Exception:
                   logger.error('sub no valido')
                   logger.error(traceback.format_exc())

        if sub:
            sub = ''
            subtitles = filetools.listdir(sub_dir)
            if subtitles:
                item.subtitle = []
            for subtitle in subtitles:
                if spanish and ('spa' not in subtitle or 'esp' not in subtitle or 'cas' not in subtitle):
                    continue
                item.subtitle += [filetools.join(sub_dir, subtitle)]
                break
            for subtitle in subtitles:
                if subtitle not in item.subtitle:
                    item.subtitle += [filetools.join(sub_dir, subtitle)]

    except Exception:
        logger.error(traceback.format_exc())

    return sub


def get_from_subdl(sub_url, sub_data=None, sub_dir='', item=Item()):

    """
    :param sub_url: Url de descarga del subtitulo alojado en suvdivx.com
           Por Ejemplo: https://subdl.com/subtitle/sd12674668/it-ends-with-us

    :return: La ruta al subtitulo descomprimido
    """

    logger.info()

    sub = []
    sub_data = ''
    sub_url_alt = 'https://dl.%s/subtitle/' % httptools.obtain_domain(sub_url, scheme=False).rstrip('/')
    sub_url = sub_url.replace("&amp;", "&")
    if not sub_dir:
        sub_dir = filetools.join(config.get_videolibrary_path(), "subtitles")
        filetools.mkdir(sub_dir)

    if not sub_data:
        sub_data = httptools.downloadpage(sub_url, **kwargs)
        if not sub_data.sucess:
            return sub_url

        sub_titles_txt = scrapertools.find_single_match(sub_data.data, r'(\{\\"groupedSubtitles\\".*?)\,\\"subtitleSimpleParsed\\"')\
                                                        .replace('\\\\\\"', '@').replace('\\', '') + '}'
        if not sub_titles_txt:
            logger.debug(sub_data.data)
            return sub_url
        sub_titles = jsontools.load(sub_titles_txt)
        if not sub_titles:
            logger.debug(sub_titles_txt)
            return sub_url

        for language in ['spanish', 'english']:
            if sub_titles.get('groupedSubtitles', {}).get(language):
                for sub_title in sub_titles['groupedSubtitles'][language]:
                    if sub_title.get('quality', '') not in ['webdl', 'bluray']:
                        continue
                    link = sub_url_alt + sub_title.get('link', '')
                    file_id = '%s.zip' % sub_title.get('title', '')
                    filename = os.path.join(sub_dir, file_id)
                    try:
                        data_dl = httptools.downloadpage(link, **kwargs).data
                        filetools.write(filename, data_dl)
                        sub += [extract_file_online(sub_dir, filename)]
                        if sub and filetools.exists(filename):
                            filetools.remove(filename)
                        break
                    except Exception:
                       logger.info('sub no valido')

    else:
       logger.info('sub no valido')
    return sub


def extract_file_online(path, filename):

    """
    :param path: Ruta donde se encuentra el archivo comprimido

    :param filename: Nombre del archivo comprimido

    :return: Devuelve la ruta al subtitulo descomprimido
    """

    logger.info()

    url = "http://online.b1.org/rest/online/upload"

    data = httptools.downloadpage(url, file=filename, **kwargs).data

    result = jsontools.load(scrapertools.find_single_match(data, r"result.listing = ([^;]+);"))
    compressed = result["name"]
    extracted = result["children"][0]["name"]

    dl_url = "http://online.b1.org/rest/online/download/%s/%s" % (compressed, extracted)
    extracted_path = os.path.join(path, extracted)
    data_dl = httptools.downloadpage(dl_url, **kwargs).data
    filetools.write(extracted_path, data_dl)

    return extracted_path


def download_subtitles(item):
    #Permite preparar la descarga de los subtítulos externos
    logger.info(item.subtitle)

    subtitle_services = [['subscene.com', get_from_subscene], ['subdivx.com', get_from_subdivx], ['subdl.com', get_from_subdl]]

    if not item.subtitle:
        return item

    if not isinstance(item.subtitle, list):
        subtitles = [item.subtitle]
    else:
        subtitles = item.subtitle[:]
    item.subtitle = ''

    try:
        subtitles_path = config.get_kodi_setting('subtitles.custompath')
        if not subtitles_path:
            subtitles_path = filetools.join(config.get_videolibrary_path(), "subtitles")
            filetools.mkdir(subtitles_path)

        for x, subtitle in enumerate(subtitles):
            data_dl = ''
            if not subtitle.startswith('http'):
                if not item.subtitle:
                    item.subtitle = subtitle
                continue

            subtitle_path_name = filetools.join(subtitles_path, subtitle.split('/')[-1])

            for service, funtion in subtitle_services:
                if service in httptools.obtain_domain(subtitle):
                    data_dl = funtion(subtitle, data_dl, subtitles_path, item)
                    if data_dl:
                        item.subtitle = data_dl
                        if isinstance(item.subtitle, list):
                            logger.debug(item.subtitle)
                        data_dl = ''
                        break

            if not data_dl and not item.subtitle:
                data_dl = httptools.downloadpage(subtitle.replace("&amp;", "&"), soup=True, headers=item.headers or {}, **kwargs)

            if data_dl: 
                res = filetools.write(subtitle_path_name, data_dl.data)
                if res and not item.subtitle:
                    item.subtitle = subtitle_path_name
    except Exception:
        logger.error(traceback.format_exc())

    return item