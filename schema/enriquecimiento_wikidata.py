"""
Enriquecimiento de datos con Wikidata
Versión OPTIMIZADA + FILTRO GEOGRÁFICO (Solo Comunidad Valenciana)
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import re
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, OWL
import os
import sys

SCHEMA = Namespace("https://schema.org/")
EX = Namespace("http://example.org/agricultura/")
WD = Namespace("http://www.wikidata.org/entity/")
WDT = Namespace("http://www.wikidata.org/prop/direct/")

# ============================================================================
# FUNCIONES DE AYUDA
# ============================================================================

def limpiar_label_sparql(nombre):
    """
    Limpia y normaliza nombres del CSV.
    """
    if not nombre: return ""
    
    # 1. Si hay barra '/', nos quedamos solo con la primera parte
    if '/' in nombre:
        nombre = nombre.split('/')[0]
    
    # 2. Gestionar artículos: "Campello (El)" -> "El Campello"
    match = re.search(r'(.+?)\s*\((.+?)\)', nombre)
    if match:
        cuerpo = match.group(1).strip()
        articulo = match.group(2).strip()
        articulos_comunes = ['el', 'la', 'los', 'las', "l'", 'els', 'les']
        if articulo.lower() in articulos_comunes:
            nombre = f"{articulo} {cuerpo}"
        else:
            nombre = cuerpo

    # 3. Limpieza general
    nombre = nombre.strip().replace("'", "\\'")
    return nombre

# ============================================================================
# CLASE PRINCIPAL
# ============================================================================

class WikidataEnricher:
    """Clase para enriquecer datos con Wikidata usando Búsqueda Optimizada"""
    
    def __init__(self, grafo):
        self.g = grafo
        self.g.bind("wd", WD)
        self.g.bind("wdt", WDT)
        self.g.bind("owl", OWL)
        self.cache = {}
        
        # Sesión robusta
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        
    def buscar_entidad(self, nombre, tipo="municipio"):
        """
        Busca usando el servicio MWAPI y filtra por geografía.
        """
        nombre_limpio = limpiar_label_sparql(nombre) 
        
        # Cache
        cache_key = f"{tipo}_{nombre_limpio}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # CONSULTA OPTIMIZADA: Usamos el buscador de texto primero
        if tipo == "municipio":
            query = f"""
            SELECT ?item ?itemLabel ?coord ?poblacion WHERE {{
              SERVICE wikibase:mwapi {{
                  bd:serviceParam wikibase:api "EntitySearch" .
                  bd:serviceParam wikibase:endpoint "www.wikidata.org" .
                  bd:serviceParam mwapi:search "{nombre_limpio}" .
                  bd:serviceParam mwapi:language "es" .
                  ?item wikibase:apiOutputItem mwapi:item .
              }}
              
              # 1. Filtro: Debe ser un municipio (o entidad administrativa)
              ?item wdt:P31/wdt:P279* wd:Q2074737 . 

              # 2. FILTRO GEOGRAFICO CRITICO:
              # El ítem debe estar localizado en (P131) la Comunidad Valenciana (Q5720)
              # El asterisco * busca recursivamente (Pueblo -> Comarca -> Provincia -> CV)
              ?item wdt:P131* wd:Q5720 .
              
              OPTIONAL {{ ?item wdt:P625 ?coord }}
              OPTIONAL {{ ?item wdt:P1082 ?poblacion }}
              
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es". }}
            }}
            LIMIT 1
            """
        elif tipo == "cultivo":
            query = f"""
            SELECT ?item ?itemLabel ?taxon WHERE {{
              SERVICE wikibase:mwapi {{
                  bd:serviceParam wikibase:api "EntitySearch" .
                  bd:serviceParam wikibase:endpoint "www.wikidata.org" .
                  bd:serviceParam mwapi:search "{nombre_limpio}" .
                  bd:serviceParam mwapi:language "es" .
                  ?item wikibase:apiOutputItem mwapi:item .
              }}
              
              # Filtramos por tipos agrícolas
              ?item wdt:P31/wdt:P279* ?tipo .
              FILTER(?tipo IN (wd:Q25403900, wd:Q43263, wd:Q11344, wd:Q10998, wd:Q756, wd:Q5255892, wd:Q23392))
              
              OPTIONAL {{ ?item wdt:P225 ?taxon }}
              
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es". }}
            }}
            LIMIT 1
            """
        else:
            return None
        
        url = "https://query.wikidata.org/sparql"
        headers = {'User-Agent': 'AguaAgricolaBot/1.0 (Student Project)'}
        
        try:
            response = self.session.get(
                url, 
                params={'query': query, 'format': 'json'},
                headers=headers,
                timeout=20 
            )
            
            if response.status_code == 200:
                data = response.json()
                if data['results']['bindings']:
                    resultado = data['results']['bindings'][0]
                    self.cache[cache_key] = resultado
                    return resultado
            
        except Exception as e:
            print(f"[ERROR] ({type(e).__name__}) con '{nombre_limpio}'")
        
        return None
    
    def enriquecer_municipio(self, uri_municipio, nombre):
        resultado = self.buscar_entidad(nombre, "municipio")
        if resultado:
            wikidata_uri = URIRef(resultado['item']['value'])
            self.g.add((uri_municipio, OWL.sameAs, wikidata_uri))
            
            if 'coord' in resultado:
                coord = resultado['coord']['value']
                if 'Point' in coord:
                    try:
                        lon_lat = coord.replace('Point(', '').replace(')', '').split()
                        geo_uri = URIRef(f"{uri_municipio}/geo")
                        self.g.add((geo_uri, RDF.type, SCHEMA.GeoCoordinates))
                        self.g.add((geo_uri, SCHEMA.longitude, Literal(float(lon_lat[0]))))
                        self.g.add((geo_uri, SCHEMA.latitude, Literal(float(lon_lat[1]))))
                        self.g.add((uri_municipio, SCHEMA.geo, geo_uri))
                    except: pass
            
            if 'poblacion' in resultado:
                self.g.add((uri_municipio, SCHEMA.population, Literal(int(resultado['poblacion']['value']))))
            return True
        return False
    
    def enriquecer_cultivo(self, uri_cultivo, nombre):
        resultado = self.buscar_entidad(nombre, "cultivo")
        if resultado:
            wikidata_uri = URIRef(resultado['item']['value'])
            self.g.add((uri_cultivo, OWL.sameAs, wikidata_uri))
            if 'taxon' in resultado:
                self.g.add((uri_cultivo, SCHEMA.additionalProperty, Literal(f"Taxón: {resultado['taxon']['value']}", lang="la")))
            return True
        return False
    
    def enriquecer_grafo(self, max_municipios=50, max_cultivos=50):
        """Enriquece el grafo completo"""
        print("\n" + "="*60)
        print("ENRIQUECIMIENTO CON WIKIDATA (Filtro C. Valenciana)")
        print("="*60)
        
        # MUNICIPIOS
        municipios = set()
        for s in self.g.subjects(SCHEMA.additionalType, Literal("municipio", lang="es")):
            n = list(self.g.objects(s, SCHEMA.name))
            if n: municipios.add((s, str(n[0])))
        
        print(f"\nMunicipios encontrados: {len(municipios)}")
        lista_m = list(municipios)
        enriquecidos_m = 0
        
        for i, (uri, nombre) in enumerate(lista_m[:max_municipios]):
            if self.enriquecer_municipio(uri, nombre): enriquecidos_m += 1
            if (i+1) % 10 == 0: print(f"   [INFO] Municipios: {i+1}/{max_municipios} (Encontrados: {enriquecidos_m})")
            
        print(f"Total Municipios encontrados en Wikidata: {enriquecidos_m}")
        
        # CULTIVOS
        cultivos = set()
        for s in self.g.subjects(RDF.type, SCHEMA.Product):
            n = list(self.g.objects(s, SCHEMA.name))
            if n: cultivos.add((s, str(n[0])))
            
        print(f"\nCultivos encontrados: {len(cultivos)}")
        lista_c = list(cultivos)
        enriquecidos_c = 0
        
        for i, (uri, nombre) in enumerate(lista_c[:max_cultivos]):
            if self.enriquecer_cultivo(uri, nombre): enriquecidos_c += 1
            else: print(f"    [!] No encontrado: {nombre}")
            
            if (i+1) % 5 == 0: print(f"   [INFO] Cultivos: {i+1}/{max_cultivos} (Encontrados: {enriquecidos_c})")
            
        print(f"   Total Cultivos encontrados: {enriquecidos_c}")

def aplicar_enriquecimiento(archivo_rdf='outputs/datos_agricolas.ttl'):
    print("="*60)
    print("INICIANDO PROCESO")
    print("="*60)
    
    if not os.path.exists(archivo_rdf):
        print(f"[ERROR] {archivo_rdf} no encontrado")
        return

    g = Graph()
    g.parse(archivo_rdf, format='turtle')
    print(f"[OK] Grafo cargado: {len(g):,} tripletas")
    
    enricher = WikidataEnricher(g)
    
    # IMPORTANTE: He subido esto a 500 para asegurarnos de que procesa
    # TODOS los municipios y arregla el de Torrella.
    enricher.enriquecer_grafo(max_municipios=600, max_cultivos=50)
    
    archivo_salida = archivo_rdf.replace('.ttl', '_enriquecido.ttl')
    g.serialize(destination=archivo_salida, format='turtle')
    print(f"\n[OK] Guardado en: {archivo_salida}")

if __name__ == "__main__":
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    os.chdir(SCRIPT_DIR)
    
    print(f"Directorio de trabajo: {SCRIPT_DIR}")
    
    # RUTA CORRECTA: Busca dentro de outputs
    aplicar_enriquecimiento('outputs/datos_agricolas.ttl')