# -*- coding: utf-8 -*-
# -*- Channel Pelisplus -*-
# -*- Created for Alfa-addon -*-
# -*- By the Alfa Develop Group -*-

import sys
PY3 = False
if sys.version_info[0] >= 3: PY3 = True; unicode = str; unichr = chr; long = int

if PY3:
    import urllib.parse as urlparse                                             # Es muy lento en PY2.  En PY3 es nativo
else:
    import urlparse                                                             # Usamos el nativo de PY2 que es más rápido

import re, base64

from channels import autoplay
from channels import filtertools
from core import httptools
from core import scrapertools
from core import servertools
from core import tmdb
from core.item import Item
from platformcode import config, logger
from channelselector import get_thumb
from lib import generictools
from bs4 import BeautifulSoup

list_language = ['LAT']

list_quality = []

list_servers = [
    'directo',
    'vidlox',
    'fembed',
    'uqload',
    'gounlimited',
    'fastplay',
    'mixdrop',
    'mystream'
    ]

canonical = {
             'channel': 'pelisplus', 
             'host': config.get_setting("current_host", 'pelisplus', default=''), 
             'host_alt': ["https://www.pelisplus.lat/"], 
             'host_black_list': ["https://www.pelisplus.me/", "https://pelisplushd.net/","https://pelisplushd.to/"], 
             'CF': False, 'CF_test': False, 'alfa_s': True
            }
host = canonical['host'] or canonical['host_alt'][0]
patron_domain = '(?:http.*\:)?\/\/(?:.*ww[^\.]*)?\.?(?:[^\.]+\.)?([\w|\-]+\.\w+)(?:\/|\?|$)'
domain = scrapertools.find_single_match(host, patron_domain)


def mainlist(item):
    logger.info()
    
    autoplay.init(item.channel, list_servers, list_quality)

    itemlist = list()

    itemlist.append(Item(channel=item.channel, title="Peliculas", action="sub_menu", url_todas = "peliculas", url_populares = "peliculas-polulares",
                         thumbnail=get_thumb('movies', auto=True)))

    itemlist.append(Item(channel=item.channel, title="Series", action="sub_menu", url_todas = "ver-series",
                         thumbnail=get_thumb('tvshows', auto=True)))

    itemlist.append(Item(channel=item.channel, title="Anime", action="sub_menu", url_todas ="ver-animes",
                         thumbnail=get_thumb('anime', auto=True)))

    itemlist.append(Item(channel=item.channel, title="Doramas", action="list_all", url=host + "doramas",
                         content="serie", thumbnail=get_thumb('doramas', auto=True)))

    itemlist.append(Item(channel=item.channel, title="Buscar", action="search", url=host + '?s=',
                         thumbnail=get_thumb('search', auto=True)))

    autoplay.show_option(item.channel, itemlist)

    return itemlist


def sub_menu(item):
    logger.info()
    itemlist = list()

    if item.title.lower() == "anime":
        content = item.title.lower()
        item.title = "Animes"
    else:
        content = item.title.lower()[:-1]

    itemlist.append(Item(channel=item.channel, title="Todas", action="list_all", url=host + '%s' % item.url_todas,
                         thumbnail=get_thumb('all', auto=True)))

    if item.title.lower() == "peliculas":
        itemlist.append(Item(channel=item.channel, title="Ultimos polulares", action="list_all",
                            url=host + 'peliculas-populares',
                            thumbnail=get_thumb('more watched', auto=True), type=content))
        itemlist.append(Item(channel=item.channel, title="Peliculas estreno", action="list_all",
                            url=host + '/estrenos',
                            thumbnail=get_thumb('more watched', auto=True), type=content))
        itemlist.append(Item(channel=item.channel, title="Generos", action="section",
                             thumbnail=get_thumb('genres', auto=True), type=content))
    elif item.title.lower() == "series":
        itemlist.append(Item(channel=item.channel, title="Ultimos estrenos", action="list_all",
                             url=host + 'series-en-estreno', thumbnail=get_thumb('more watched', auto=True), type=content))
        itemlist.append(Item(channel=item.channel, title="Mas Vistas", action="list_all",
                             url=host + 'series-populares', thumbnail=get_thumb('more watched', auto=True), type=content))
    return itemlist


def create_soup(url, referer=None, unescape=False):
    logger.info()

    if referer:
        data = httptools.downloadpage(url, headers={'Referer': referer}, canonical=canonical).data
    else:
        data = httptools.downloadpage(url, canonical=canonical).data

    if unescape:
        data = scrapertools.unescape(data)
    soup = BeautifulSoup(data, "html5lib", from_encoding="utf-8")

    return soup


def list_all(item):
    logger.info()
    itemlist = list()

    soup = create_soup(item.url)

    matches = soup.find("div", class_="Posters")

    for elem in matches.find_all("a"):
        url = urlparse.urljoin(host, elem["href"])
        thumb = urlparse.urljoin(host, elem.img["src"])
        title = scrapertools.find_single_match(elem.p.text, r"(.*?) \(")
        year = scrapertools.find_single_match(elem.p.text, r"(\d{4})")
        if not year:
            year = "-"
            title = elem.p.text
        if item.type and item.type.lower() not in url:
            continue
        new_item = Item(channel=item.channel, title=title, url=url, thumbnail=thumb, infoLabels={"year": year})

        if "/pelicula/" in url:
            new_item.contentTitle = title
            new_item.action = "findvideos"
        else:
            new_item.contentSerieName = title
            new_item.action = "seasons"

        itemlist.append(new_item)
    tmdb.set_infoLabels_itemlist(itemlist, True)
    #  Paginación

    try:
        next_page = soup.find("a", class_="page-link", rel="next")["href"]

        if next_page:
            if not next_page.startswith(host):
                next_page = host + next_page
            itemlist.append(Item(channel=item.channel, title="Siguiente >>", url=next_page, action='list_all'))
    except:
        pass

    return itemlist


def seasons(item):
    logger.info()

    itemlist = list()
    soup = create_soup(item.url).find("ul", class_="TbVideoNv nav nav-tabs")
    matches = soup.find_all("li")
    infoLabels = item.infoLabels

    for elem in matches:
        title = " ".join(elem.a.text.split()).capitalize()
        infoLabels["season"] = scrapertools.find_single_match(title, "Temporada (\d+)")
        itemlist.append(Item(channel=item.channel, title=title, url=item.url, action='episodesxseasons',
                             infoLabels=infoLabels))
    tmdb.set_infoLabels_itemlist(itemlist, seekTmdb=True)

    if config.get_videolibrary_support() and len(itemlist) > 0:
        itemlist.append(
            Item(channel=item.channel, title='[COLOR yellow]Añadir esta serie a la videoteca[/COLOR]', url=item.url,
                 action="add_serie_to_library", extra="episodios", contentSerieName=item.contentSerieName))

    return itemlist


def episodios(item):
    logger.info()
    itemlist = []
    templist = seasons(item)
    for tempitem in templist:
        itemlist += episodesxseasons(tempitem)

    return itemlist


def episodesxseasons(item):
    logger.info()

    data = httptools.downloadpage(item.url).data
    itemlist = list()
    infoLabels = item.infoLabels
    season = infoLabels["season"]
    bloque = scrapertools.find_single_match(data, '(?is)role="tabpanel" class=".*id="%s".*?</div' %item.contentSeason)
    patron  = 'href="([^"]+).*?'
    patron += 'btn-block">([^<]+)'
    matches = scrapertools.find_multiple_matches(bloque, patron)
    if not matches:
        return itemlist

    for url, episodio in matches:
        epi_num = scrapertools.find_single_match(episodio, "E(\d+)")
        epi_name = scrapertools.find_single_match(episodio, ":([^$]+)")
        infoLabels['episode'] = epi_num
        title = '%sx%s - %s' % (season, epi_num, epi_name.strip())

        itemlist.append(Item(channel=item.channel, title=title, url=url, action='findvideos', infoLabels=infoLabels))

    tmdb.set_infoLabels_itemlist(itemlist, seekTmdb=True)

    return itemlist


def section(item):
    logger.info()
    itemlist = list()
    data = httptools.downloadpage(host).data
    patron  = '(%sgenero/[^"]+)' %host
    patron += '">([^<]+)'
    matches = scrapertools.find_multiple_matches(data, patron)
    for url, title in matches:
        itemlist.append(Item(channel=item.channel, url=url, title=title, action='list_all', type=item.type))

    return itemlist


def findvideos(item):
    logger.info()

    itemlist = list()

    data = httptools.downloadpage(item.url, forced_proxy_opt='ProxyCF', canonical=canonical)

    if data.sucess or data.code == 302:
        data = data.data
    pattern = 'data-tr="([^"]+)"'
    matches = scrapertools.find_multiple_matches(data, pattern)
    encontrados = []
    for url in matches:
        url = base64.b64decode(url)
        if PY3 and isinstance(url, bytes):
            url = "".join(chr(x) for x in bytes(url))
        if not "http" in url:
            url = "https://www.pelisplus.lat" + url
        if "pelisplus.lat" in url:
            prueba = httptools.downloadpage(url).data
            url = scrapertools.find_single_match(prueba, "(?is)window.location.href = '([^']+)")
            if not url.startswith("http"):  url = "https:" + url
        if "plusto.link" in url: url = url.replace("plusto.link","fembed.com")
        if url in encontrados: continue
        encontrados.append(url)
        itemlist.append(Item(channel=item.channel, title='%s [%s]', url=url, action='play', language="LAT",
        infoLabels=item.infoLabels))

    itemlist = servertools.get_servers_itemlist(itemlist, lambda i: i.title % (i.server.capitalize(), i.language))

    # Requerido para FilterTools

    itemlist = filtertools.get_links(itemlist, item, list_language)

    # Requerido para AutoPlay

    autoplay.start(itemlist, item)

    if item.contentType == 'movie':
        if config.get_videolibrary_support() and len(itemlist) > 0 and item.extra != 'findvideos':
            itemlist.append(Item(channel=item.channel,
                                 title='[COLOR yellow]Añadir esta pelicula a la videoteca[/COLOR]',
                                 url=item.url,
                                 action="add_pelicula_to_library",
                                 extra="findvideos",
                                 contentTitle=item.contentTitle))
    return itemlist


def play(item):
    logger.info()
    if "apialfa.tomatomatela.com" in item.url:
        data = httptools.downloadpage(item.url).data
        hostx = "https://apialfa.tomatomatela.com/ir/"
        item.url = hostx + scrapertools.find_single_match(data, 'id="link" href="([^"]+)')
        data = httptools.downloadpage(item.url).data
        xvalue = scrapertools.find_single_match(data, 'name="url" value="([^"]+)')
        post = {"url" : xvalue}
        item.url = httptools.downloadpage(hostx + "rd.php", follow_redirects=False, post=post).headers.get("location", "")
        data = httptools.downloadpage("https:" + item.url).data
        xvalue = scrapertools.find_single_match(data, 'name="url" value="([^"]+)')
        post = {"url" : xvalue}
        item.url = httptools.downloadpage(hostx + "redirect_ddh.php", follow_redirects=False, post=post).headers.get("location", "")
        hash = scrapertools.find_single_match(item.url,"#(\w+)")
        file = httptools.downloadpage("https://tomatomatela.com/details.php?v=%s" %hash).json
        item.url = file["file"]
        dd = httptools.downloadpage(item.url, only_headers=True).data
    return [item]


def search(item, texto):
    logger.info()
    texto = texto.replace(" ", "+")
    item.url += texto

    try:
        if texto != '':
            return list_all(item)
        else:
            return []
    except:
        import sys
        for line in sys.exc_info():
            logger.error("%s" % line)
        return []


def newest(categoria):
    logger.info()

    item = Item()
    try:
        if categoria in ['peliculas', 'latino']:
            item.url = host + 'peliculas/estrenos'
        elif categoria == 'infantiles':
            item.url = host + 'generos/animacion/'
        elif categoria == 'terror':
            item.url = host + 'generos/terror/'
        itemlist = list_all(item)
        if itemlist[-1].title == 'Siguiente >>':
            itemlist.pop()
    except:
        import sys
        for line in sys.exc_info():
            logger.error("{0}".format(line))
        return []

    return itemlist
