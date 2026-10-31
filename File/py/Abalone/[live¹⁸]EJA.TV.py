# -*- coding: utf-8 -*-
"""
Eja.tv IPTV Spider - Auto Detect dari HTML + Logo
Untuk OK影视 / IPTV Player
"""

import re
import requests
from urllib.parse import urljoin, quote, urlparse, parse_qs
from bs4 import BeautifulSoup
from base.spider import Spider


class Spider(Spider):
    def init(self, extend=""):
        """Inisialisasi spider"""
        self.site = 'https://eja.tv'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': self.site,
        }
        self.session = requests.Session()
        self.per_page = 20
        self.channels_per_page = 6
        
        # Cache untuk negara
        self.countries_cache = None
        
    def getName(self):
        return "🌍 EJA.TV IPTV"
    
    def isVideoFormat(self, url):
        return '.m3u8' in url.lower() or '.mpd' in url.lower() if url else False
    
    def _get_countries_from_html(self):
        """Ambil daftar negara dari HTML website"""
        if self.countries_cache is not None:
            return self.countries_cache
        
        countries = {'all': '🌍 Semua Negara'}
        
        try:
            response = self.session.get(self.site, headers=self.headers, timeout=30)
            if response.status_code != 200:
                return countries
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Cari SELECT dropdown negara (jika ada)
            select = soup.find('select', {'name': 'country'})
            if select:
                options = select.find_all('option')
                for opt in options:
                    code = opt.get('value', '')
                    name = opt.text.strip()
                    if code and name:
                        flag_match = re.search(r'[🇦-🇿]+', name)
                        if flag_match:
                            flag = flag_match.group()
                            name_clean = re.sub(r'[🇦-🇿]+', '', name).strip()
                            countries[code] = f"{flag} {name_clean}"
                        else:
                            countries[code] = name
            
            # Cari link country di halaman
            country_links = soup.find_all('a', href=lambda x: x and 'country=' in x)
            
            for link in country_links:
                href = link.get('href', '')
                code = self._get_param(href, 'country')
                if code and code not in countries:
                    text = link.text.strip()
                    name = re.sub(r'[🇦-🇿]+', '', text).strip()
                    flag = re.search(r'[🇦-🇿]+', text)
                    flag_emoji = flag.group() if flag else ''
                    countries[code] = f"{flag_emoji} {name}" if name else text
            
            print(f"Found {len(countries)-1} countries from HTML")
            self.countries_cache = countries
            return countries
            
        except Exception as e:
            print(f"Error getting countries from HTML: {e}")
            # Fallback
            fallback = {
                'all': '🌍 Semua Negara',
                'id': '🇮🇩 Indonesia',
                'my': '🇲🇾 Malaysia',
                'us': '🇺🇸 United States',
                'gb': '🇬🇧 United Kingdom',
                'it': '🇮🇹 Italy',
                'fr': '🇫🇷 France',
                'de': '🇩🇪 Germany',
                'es': '🇪🇸 Spain',
                'pt': '🇵🇹 Portugal',
                'nl': '🇳🇱 Netherlands',
                'ru': '🇷🇺 Russia',
                'cn': '🇨🇳 China',
                'jp': '🇯🇵 Japan',
                'kr': '🇰🇷 South Korea',
                'in': '🇮🇳 India',
                'br': '🇧🇷 Brazil',
                'mx': '🇲🇽 Mexico',
                'ar': '🇦🇷 Argentina',
                'au': '🇦🇺 Australia',
                'ca': '🇨🇦 Canada',
                'sg': '🇸🇬 Singapore',
                'ph': '🇵🇭 Philippines',
                'th': '🇹🇭 Thailand',
                'vn': '🇻🇳 Vietnam',
                'tr': '🇹🇷 Turkey',
                'sa': '🇸🇦 Saudi Arabia',
                'ae': '🇦🇪 UAE',
                'eg': '🇪🇬 Egypt',
                'za': '🇿🇦 South Africa',
                'ng': '🇳🇬 Nigeria',
                'ke': '🇰🇪 Kenya',
                'pk': '🇵🇰 Pakistan',
                'bd': '🇧🇩 Bangladesh',
                'mm': '🇲🇲 Myanmar',
                'kh': '🇰🇭 Cambodia',
                'la': '🇱🇦 Laos',
                'mn': '🇲🇳 Mongolia',
                'np': '🇳🇵 Nepal',
                'lk': '🇱🇰 Sri Lanka',
                'tw': '🇹🇼 Taiwan',
                'hk': '🇭🇰 Hong Kong',
                'mo': '🇲🇴 Macau',
                'il': '🇮🇱 Israel',
                'ir': '🇮🇷 Iran',
                'iq': '🇮🇶 Iraq',
                'jo': '🇯🇴 Jordan',
                'lb': '🇱🇧 Lebanon',
                'sy': '🇸🇾 Syria',
                'ye': '🇾🇪 Yemen',
                'ma': '🇲🇦 Morocco',
                'dz': '🇩🇿 Algeria',
                'tn': '🇹🇳 Tunisia',
                'ly': '🇱🇾 Libya',
                'sd': '🇸🇩 Sudan',
                'et': '🇪🇹 Ethiopia',
                'gh': '🇬🇭 Ghana',
                'ug': '🇺🇬 Uganda',
                'tz': '🇹🇿 Tanzania',
                'zm': '🇿🇲 Zambia',
                'zw': '🇿🇼 Zimbabwe',
                'at': '🇦🇹 Austria',
                'be': '🇧🇪 Belgium',
                'bg': '🇧🇬 Bulgaria',
                'hr': '🇭🇷 Croatia',
                'cy': '🇨🇾 Cyprus',
                'cz': '🇨🇿 Czech Republic',
                'dk': '🇩🇰 Denmark',
                'ee': '🇪🇪 Estonia',
                'fi': '🇫🇮 Finland',
                'gr': '🇬🇷 Greece',
                'hu': '🇭🇺 Hungary',
                'ie': '🇮🇪 Ireland',
                'lv': '🇱🇻 Latvia',
                'lt': '🇱🇹 Lithuania',
                'lu': '🇱🇺 Luxembourg',
                'mt': '🇲🇹 Malta',
                'md': '🇲🇩 Moldova',
                'me': '🇲🇪 Montenegro',
                'no': '🇳🇴 Norway',
                'pl': '🇵🇱 Poland',
                'ro': '🇷🇴 Romania',
                'rs': '🇷🇸 Serbia',
                'sk': '🇸🇰 Slovakia',
                'si': '🇸🇮 Slovenia',
                'se': '🇸🇪 Sweden',
                'ch': '🇨🇭 Switzerland',
                'ua': '🇺🇦 Ukraine',
                'uz': '🇺🇿 Uzbekistan',
                'kz': '🇰🇿 Kazakhstan',
                'az': '🇦🇿 Azerbaijan',
                'ge': '🇬🇪 Georgia',
                'am': '🇦🇲 Armenia',
                'al': '🇦🇱 Albania',
                'ba': '🇧🇦 Bosnia',
                'mk': '🇲🇰 North Macedonia',
                'by': '🇧🇾 Belarus',
                'is': '🇮🇸 Iceland',
                'li': '🇱🇮 Liechtenstein',
                'mc': '🇲🇨 Monaco',
                'sm': '🇸🇲 San Marino',
                'va': '🇻🇦 Vatican City',
                'ad': '🇦🇩 Andorra',
            }
            self.countries_cache = fallback
            return fallback
    
    def _get_channel_logo(self, channel_name, country_code=''):
        """Coba dapatkan logo channel dari berbagai sumber"""
        logo = ''
        
        # 1. Coba dari flagcdn (jika ada country code)
        if country_code:
            logo = f"https://flagcdn.com/32x24/{country_code}.png"
        
        # 2. Coba dari UI Avatars (generate dari nama channel)
        if not logo or logo == '':
            # Buat logo dari inisial
            name_parts = channel_name.split()
            initials = ''.join([part[0].upper() for part in name_parts[:2]])
            if not initials:
                initials = channel_name[:2].upper()
            logo = f"https://ui-avatars.com/api/?name={initials}&background=random&color=fff&size=32"
        
        # 3. Coba dari logo Clearbit (jika ada domain)
        # Tidak semua channel punya domain
        
        return logo
    
    def homeContent(self, filter):
        """Home content dengan kategori dari HTML"""
        countries = self._get_countries_from_html()
        
        categories = []
        for code, name in countries.items():
            if code == 'all':
                categories.insert(0, {'type_id': 'all', 'type_name': name})
            else:
                categories.append({'type_id': code, 'type_name': name})
        
        return {
            'class': categories,
            'filters': {}
        }
    
    def _get_html(self, url):
        """Get HTML dengan error handling"""
        try:
            response = self.session.get(url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                return response.text
            else:
                print(f"Status code: {response.status_code}")
                return None
        except Exception as e:
            print(f"Error: {e}")
            return None
    
    def _fetch_channels(self, country='', page=1):
        """Fetch channel dari eja.tv dengan pagination"""
        offset = (page - 1) * self.channels_per_page
        
        if country and country.strip() and country != 'all':
            url = f"{self.site}/?country={country}"
            if offset > 0:
                url += f"&offset={offset}"
        else:
            url = self.site
            if offset > 0:
                url += f"?offset={offset}"
        
        print(f"Fetching page {page}: {url}")
        
        html = self._get_html(url)
        if not html:
            return [], 0, 0
        
        return self._parse_html(html, page)
    
    def _parse_html(self, html, current_page=1):
        """Parse HTML dan ekstrak channel"""
        channels = []
        soup = BeautifulSoup(html, 'html.parser')
        
        cards = soup.find_all('div', class_='card')
        print(f"Found {len(cards)} cards on page {current_page}")
        
        if not cards:
            cards = soup.select('.card')
            print(f"Found {len(cards)} cards with selector")
        
        for card in cards:
            channel = self._parse_card(card)
            if channel:
                channels.append(channel)
        
        # Total channel
        total = 0
        total_text = soup.find('small')
        if total_text:
            patterns = [
                r'(\d+)\s+channels',
                r'(\d+)\s+live\s+iptv\s+channels',
                r'(\d+)\s+iptv\s+channels',
                r'(\d+)\s+tv\s+channels'
            ]
            for pattern in patterns:
                match = re.search(pattern, total_text.text, re.IGNORECASE)
                if match:
                    total = int(match.group(1))
                    break
        
        if total == 0:
            pagination = soup.find('ul', class_='pagination')
            if pagination:
                links = pagination.find_all('a')
                max_offset = 0
                for link in links:
                    href = link.get('href', '')
                    if 'offset=' in href:
                        off = self._get_param(href, 'offset')
                        if off and off.isdigit():
                            max_offset = max(max_offset, int(off))
                if max_offset > 0:
                    total = max_offset + self.channels_per_page
        
        total_pages = 1
        if total > 0:
            total_pages = (total + self.channels_per_page - 1) // self.channels_per_page
        
        print(f"Page {current_page}: parsed {len(channels)} channels, total {total}, total_pages {total_pages}")
        
        return channels, total, total_pages
    
    def _parse_card(self, card):
        """Parse satu card channel"""
        try:
            channel = {}
            
            # Nama channel
            title = card.find('h5', class_='card-title')
            if title:
                name_span = title.find('span', class_='text-muted')
                channel['name'] = name_span.text.strip() if name_span else title.text.strip()
            else:
                title = card.find('h5')
                if title:
                    channel['name'] = title.text.strip()
                else:
                    return None
            
            # Stream URL
            video = card.find('video')
            if video:
                # Poster / Thumbnail
                poster = video.get('poster', '')
                if poster:
                    if poster.startswith('/'):
                        channel['poster'] = urljoin(self.site, poster)
                    else:
                        channel['poster'] = poster
                else:
                    channel['poster'] = ''
                
                # Source
                source = video.find('source')
                if source:
                    src = source.get('src', '')
                    if '#' in src:
                        channel['stream_url'] = src.split('#')[0]
                    else:
                        channel['stream_url'] = src
                else:
                    channel['stream_url'] = ''
            else:
                channel['stream_url'] = ''
                channel['poster'] = ''
            
            if not channel.get('stream_url'):
                return None
            
            # Negara
            country_link = card.find('a', href=lambda x: x and 'country=' in x)
            if country_link:
                country_text = country_link.text.strip()
                country_text = re.sub(r'[🇦-🇿]+', '', country_text).strip()
                channel['country'] = country_text
                channel['country_code'] = self._get_param(country_link.get('href', ''), 'country')
            else:
                channel['country'] = ''
                channel['country_code'] = ''
            
            # Kualitas
            if card.find('i', class_='bi-badge-4k'):
                channel['quality'] = '4K'
            elif card.find('i', class_='bi-badge-fhd'):
                channel['quality'] = 'FHD'
            elif card.find('i', class_='bi-badge-hd'):
                channel['quality'] = 'HD'
            else:
                channel['quality'] = 'SD'
            
            # Logo - Gunakan poster jika ada, fallback ke flag atau generated
            if channel.get('poster'):
                channel['logo'] = channel['poster']
            elif channel.get('country_code'):
                channel['logo'] = f"https://flagcdn.com/32x24/{channel['country_code']}.png"
            else:
                # Generate logo dari nama channel
                channel['logo'] = self._get_channel_logo(channel['name'], channel.get('country_code', ''))
            
            return channel
            
        except Exception as e:
            print(f"Error parsing card: {e}")
            return None
    
    def _get_param(self, url, param):
        """Extract parameter dari URL"""
        if not url:
            return ''
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        return params.get(param, [''])[0]
    
    def _get_flag(self, country_code):
        """Get flag emoji"""
        if not country_code or len(country_code) != 2:
            return ''
        try:
            return ''.join([chr(ord(c.upper()) - ord('A') + 0x1F1E6) for c in country_code])
        except:
            return ''
    
    def homeVideoContent(self):
        """Video yang tampil di home - halaman 1 semua channel"""
        return self._get_home_video_content(page=1, country='all', category='all')
    
    def _get_home_video_content(self, page=1, country='all', category='all'):
        """Get home video content dengan pagination"""
        country_param = country if country and country != 'all' else ''
        
        channels, total, total_pages = self._fetch_channels(
            country=country_param,
            page=page
        )
        
        videos = []
        for idx, ch in enumerate(channels):
            name = ch.get('name', 'Unknown')
            country_name = ch.get('country', '')
            quality = ch.get('quality', 'SD')
            flag = self._get_flag(ch.get('country_code', ''))
            
            display_name = name
            if country_name:
                display_name += f" {flag}{country_name}"
            
            vod_id = f"{category}_{page}_{idx + 1}"
            
            videos.append({
                'vod_id': vod_id,
                'vod_name': display_name,
                'vod_pic': ch.get('logo', '') or ch.get('poster', ''),
                'vod_remarks': f"🟢 {quality}",
                'vod_year': '2026',
                'vod_area': country_name,
                'vod_content': f"📺 {name}\n\n🌍 {country_name}\n📶 {quality}",
                'vod_play_from': 'EJA.TV',
                'vod_play_url': f"{name}${ch.get('stream_url', '')}"
            })
        
        result = {
            'list': videos,
            'page': page,
            'pagecount': total_pages if total_pages > 0 else 1,
            'limit': self.per_page,
            'total': total
        }
        
        print(f"Returning page {page} of {result['pagecount']}, {len(videos)} videos")
        return result
    
    def categoryContent(self, tid, pg, filter, ext):
        """Category content dengan pagination"""
        pg = int(pg) if pg else 1
        
        country = tid if tid != 'all' else ''
        category = tid
        
        print(f"Category: {tid}, page: {pg}")
        
        return self._get_home_video_content(
            page=pg,
            country=country,
            category=category
        )
    
    def detailContent(self, ids):
        """Detail channel"""
        vod_id = ids[0]
        
        try:
            parts = vod_id.split('_')
            if len(parts) >= 3:
                category = parts[0]
                page = int(parts[1])
                idx = int(parts[2]) - 1
            else:
                page, idx = vod_id.split('_') if '_' in vod_id else ('1', vod_id)
                page = int(page)
                idx = int(idx) - 1
                category = 'all'
            
            country = category if category != 'all' else ''
            
            print(f"Detail: category={category}, page={page}, idx={idx}")
            
            channels, total, total_pages = self._fetch_channels(
                country=country,
                page=page
            )
            
            if 0 <= idx < len(channels):
                ch = channels[idx]
                play_url = ch.get('stream_url', '')
                if not play_url:
                    return {'list': []}
                
                name = ch.get('name', 'Unknown')
                country_name = ch.get('country', '')
                quality = ch.get('quality', 'SD')
                flag = self._get_flag(ch.get('country_code', ''))
                
                display_name = name
                if country_name:
                    display_name += f" {flag}{country_name}"
                
                detail = {
                    'vod_id': vod_id,
                    'vod_name': display_name,
                    'vod_pic': ch.get('logo', '') or ch.get('poster', ''),
                    'vod_remarks': f"🟢 {quality}",
                    'vod_year': '2026',
                    'vod_area': country_name,
                    'vod_content': f"📺 {name}\n\n🌍 {country_name}\n📶 {quality}",
                    'vod_play_from': 'EJA.TV',
                    'vod_play_url': f"{name}${play_url}"
                }
                
                return {'list': [detail]}
            else:
                print(f"Index {idx} out of range, total channels: {len(channels)}")
                
        except Exception as e:
            print(f"Detail error: {e}")
            import traceback
            traceback.print_exc()
        
        return {'list': []}
    
    def playerContent(self, flag, id, vipFlags):
        """Player content - return stream URL"""
        return {
            'parse': 0,
            'url': id,
            'header': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': self.site,
            }
        }
    
    def searchContent(self, key, quick, pg="1"):
        """Search channel dengan pagination"""
        if not key:
            return {'list': [], 'page': 1, 'pagecount': 1, 'limit': self.per_page, 'total': 0}
        
        page = int(pg) if pg else 1
        offset = (page - 1) * self.channels_per_page
        
        url = f"{self.site}/?search={quote(key)}"
        if offset > 0:
            url += f"&offset={offset}"
        
        print(f"Search: {url}")
        
        html = self._get_html(url)
        if not html:
            return {'list': [], 'page': 1, 'pagecount': 1, 'limit': self.per_page, 'total': 0}
        
        channels, total, total_pages = self._parse_html(html, page)
        
        videos = []
        for idx, ch in enumerate(channels):
            name = ch.get('name', 'Unknown')
            country = ch.get('country', '')
            quality = ch.get('quality', 'SD')
            flag = self._get_flag(ch.get('country_code', ''))
            
            display_name = name
            if country:
                display_name += f" {flag}{country}"
            
            videos.append({
                'vod_id': f"search_{page}_{idx + 1}",
                'vod_name': display_name,
                'vod_pic': ch.get('logo', '') or ch.get('poster', ''),
                'vod_remarks': f"🟢 {quality}",
                'vod_year': '2026',
                'vod_area': country,
                'vod_content': f"📺 {name}\n\n🌍 {country}\n📶 {quality}",
                'vod_play_from': 'EJA.TV',
                'vod_play_url': f"{name}${ch.get('stream_url', '')}"
            })
        
        return {
            'list': videos,
            'page': page,
            'pagecount': total_pages if total_pages > 0 else 1,
            'limit': self.per_page,
            'total': total
        }
    
    def destroy(self):
        """Cleanup"""
        self.session.close()