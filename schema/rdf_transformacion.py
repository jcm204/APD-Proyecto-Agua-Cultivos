"""
Transformación de datos agrícolas a tripletas RDF usando Schema.org
Proyecto: Consumo de Agua en el Sector Agrícola (Comunidad Valenciana)
"""

from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD
import csv
import re
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

print(f"Directorio de trabajo: {SCRIPT_DIR}\n")

# Definir namespaces
SCHEMA = Namespace("https://schema.org/")
EX = Namespace("http://example.org/agricultura/")
WIKIDATA = Namespace("http://www.wikidata.org/entity/")

# Crear grafo RDF
g = Graph()
g.bind("schema", SCHEMA)
g.bind("ex", EX)
g.bind("wd", WIKIDATA)

# ============================================================================
# FUNCIONES DE AYUDA
# ============================================================================

def limpiar_texto(texto):
    """Limpia el texto para usarlo en URIs"""
    texto = texto.strip().lower()
    texto = re.sub(r'[áàâä]', 'a', texto)
    texto = re.sub(r'[éèêë]', 'e', texto)
    texto = re.sub(r'[íìîï]', 'i', texto)
    texto = re.sub(r'[óòôö]', 'o', texto)
    texto = re.sub(r'[úùûü]', 'u', texto)
    texto = re.sub(r'[ñ]', 'n', texto)
    texto = re.sub(r'[^\w\s-]', '', texto)
    texto = re.sub(r'[-\s]+', '_', texto)
    return texto

def crear_uri(tipo, nombre):
    """Crea una URI única basada en el tipo y nombre"""
    nombre_limpio = limpiar_texto(nombre)
    return EX[f"{tipo}/{nombre_limpio}"]

def convertir_a_float(valor_str):
    """
    CORRECCIÓN: Limpia el string de números españoles (comma decimal) 
    y lo convierte a float.
    """
    return float(valor_str.strip().replace(',', '.'))


# ============================================================================
# CONSTRUCCIÓN DEL GRAFO
# ============================================================================

def agregar_lugar(nombre, tipo, contenedor=None):
    """Agrega un lugar al grafo con su jerarquía"""
    uri_lugar = crear_uri(tipo, nombre)
    
    # Tipo del lugar
    g.add((uri_lugar, RDF.type, SCHEMA.Place))
    g.add((uri_lugar, SCHEMA.name, Literal(nombre, lang="es")))
    g.add((uri_lugar, SCHEMA.additionalType, Literal(tipo, lang="es")))
    
    # Relación jerárquica
    if contenedor:
        uri_contenedor = crear_uri(contenedor["tipo"], contenedor["nombre"])
        g.add((uri_lugar, SCHEMA.containedInPlace, uri_contenedor))
    
    return uri_lugar

def agregar_cultivo(grupo, cultivo, ubicacion_uri):
    """Agrega información del cultivo al grafo"""
    uri_cultivo = crear_uri("cultivo", f"{grupo}_{cultivo}")
    
    # Tipo del cultivo
    g.add((uri_cultivo, RDF.type, SCHEMA.Product))
    g.add((uri_cultivo, SCHEMA.name, Literal(cultivo, lang="es")))
    g.add((uri_cultivo, SCHEMA.category, Literal(grupo, lang="es")))
    g.add((uri_cultivo, SCHEMA.location, ubicacion_uri))
    
    return uri_cultivo

def agregar_registro_agricola(row, contador):
    """Procesa un registro completo del CSV"""
    
    # 1. Crear jerarquía de lugares
    provincia = row["PROVINCIA"]
    comarca = row["COMARCA"]
    municipio = row["MUNICIPIO"]
    
    # Provincia
    uri_provincia = agregar_lugar(provincia, "provincia")
    
    # Comarca
    uri_comarca = agregar_lugar(
        comarca, 
        "comarca", 
        {"tipo": "provincia", "nombre": provincia}
    )
    
    # Municipio
    uri_municipio = agregar_lugar(
        municipio, 
        "municipio", 
        {"tipo": "comarca", "nombre": comarca}
    )
    
    # 2. Crear cultivo
    grupo_cultivo = row["GRUPO DE CULTIVO"]
    cultivo = row["CULTIVO"]
    uri_cultivo = agregar_cultivo(grupo_cultivo, cultivo, uri_municipio)
    
    # 3. Crear registro agrícola único para esta combinación
    uri_registro = EX[f"registro/{contador}"]
    g.add((uri_registro, RDF.type, SCHEMA.Event))
    g.add((uri_registro, SCHEMA.name, Literal(f"Cultivo de {cultivo} en {municipio}", lang="es")))
    g.add((uri_registro, SCHEMA.location, uri_municipio))
    g.add((uri_registro, SCHEMA.about, uri_cultivo))
    
    # 4. Superficie cultivada
    superficie = convertir_a_float(row["SUPERFICIE CULTIVADA (ha)"])
    uri_superficie = URIRef(f"{uri_registro}/superficie")
    g.add((uri_superficie, RDF.type, SCHEMA.QuantitativeValue))
    g.add((uri_superficie, SCHEMA.value, Literal(superficie, datatype=XSD.decimal)))
    g.add((uri_superficie, SCHEMA.unitCode, Literal("HEC")))  # Hectáreas
    g.add((uri_superficie, SCHEMA.name, Literal("Superficie cultivada", lang="es")))
    g.add((uri_registro, SCHEMA.area, uri_superficie))
    
    # 5. Dotación de agua
    dotacion = convertir_a_float(row["DOTACION (m3/ha)"])
    uri_dotacion = URIRef(f"{uri_registro}/dotacion")
    g.add((uri_dotacion, RDF.type, SCHEMA.QuantitativeValue))
    g.add((uri_dotacion, SCHEMA.value, Literal(dotacion, datatype=XSD.decimal)))
    g.add((uri_dotacion, SCHEMA.unitCode, Literal("MTQ")))  # Metros cúbicos por hectárea
    g.add((uri_dotacion, SCHEMA.name, Literal("Dotación de agua", lang="es")))
    g.add((uri_registro, SCHEMA.additionalProperty, uri_dotacion))
    
    # 6. Consumo estimado de agua
    consumo = convertir_a_float(row["CONSUMO ESTIMADO (m3)"])
    uri_consumo = URIRef(f"{uri_registro}/consumo")
    g.add((uri_consumo, RDF.type, SCHEMA.QuantitativeValue))
    g.add((uri_consumo, SCHEMA.value, Literal(consumo, datatype=XSD.decimal)))
    g.add((uri_consumo, SCHEMA.unitCode, Literal("MTQ")))  # Metros cúbicos
    g.add((uri_consumo, SCHEMA.name, Literal("Consumo estimado de agua", lang="es")))
    g.add((uri_registro, SCHEMA.additionalProperty, uri_consumo))
    
    # 7. Coste Estimado Total (euros)
    coste = convertir_a_float(row["COSTE ESTIMADO (euros)"])
    uri_coste = URIRef(f"{uri_registro}/coste")
    
    g.add((uri_coste, RDF.type, SCHEMA.MonetaryAmount))
    g.add((uri_coste, SCHEMA.value, Literal(coste, datatype=XSD.decimal)))
    g.add((uri_coste, SCHEMA.currency, Literal("EUR")))
    g.add((uri_coste, SCHEMA.name, Literal("Coste estimado de producción", lang="es")))
    
    g.add((uri_registro, SCHEMA.additionalProperty, uri_coste))

def procesar_csv(archivo_csv):
    """Procesa el archivo CSV completo"""
    contador = 0
    
    with open(archivo_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';') 
        
        for row in reader:
            contador += 1
            try:
                agregar_registro_agricola(row, contador)
                
                if contador % 100 == 0:
                    print(f"[INFO] Procesados {contador} registros...")
                    
            except Exception as e:
                print(f"[ERROR] Error en registro {contador}: {e}") 
    
    print(f"\n[OK] Total de registros procesados: {contador}")
    return contador

def generar_estadisticas():
    """Genera estadísticas del grafo generado"""
    print("\n" + "="*60)
    print("ESTADISTICAS DEL GRAFO RDF GENERADO")
    print("="*60)
    
    total_tripletas = len(g)
    print(f"\nTotal de tripletas: {total_tripletas:,}")
    
    # Contar por tipo de recurso
    tipos = {}
    for s in g.subjects(RDF.type, None):
        for tipo in g.objects(s, RDF.type):
            tipo_str = str(tipo).split('/')[-1]
            tipos[tipo_str] = tipos.get(tipo_str, 0) + 1
    
    print(f"\nRecursos por tipo:")
    for tipo, cantidad in sorted(tipos.items(), key=lambda x: x[1], reverse=True):
        print(f"   - {tipo}: {cantidad:,}")
    
    # Contar propiedades únicas
    propiedades = set()
    for s, p, o in g:
        propiedades.add(p)
    
    print(f"\nPropiedades únicas utilizadas: {len(propiedades)}")
    
    # Listar propiedades de Schema.org
    schema_props = [str(p).split('/')[-1] for p in propiedades if 'schema.org' in str(p)]
    print(f"\nPropiedades de Schema.org ({len(schema_props)}):")
    for prop in sorted(schema_props)[:15]:
        print(f"   - schema:{prop}")
    if len(schema_props) > 15:
        print(f"   ... y {len(schema_props) - 15} más")

def guardar_grafo(formato='turtle', archivo_salida='outputs/datos_agricolas'):
    """Guarda el grafo en diferentes formatos"""
    extensiones = {
        'turtle': 'ttl',
        'xml': 'rdf',
        'nt': 'nt',
        'n3': 'n3',
        'json-ld': 'jsonld'
    }
    
    ext = extensiones.get(formato, 'ttl')
    nombre_archivo = f"{archivo_salida}.{ext}"
    
    dir_salida = os.path.dirname(nombre_archivo)
    if dir_salida and not os.path.exists(dir_salida):
        os.makedirs(dir_salida)
    
    g.serialize(destination=nombre_archivo, format=formato, encoding='utf-8')
    print(f"\n[OK] Grafo guardado en formato {formato.upper()}: {nombre_archivo}")
    
    tamanio = os.path.getsize(nombre_archivo) / 1024
    print(f"   Tamaño: {tamanio:.2f} KB")

def mostrar_ejemplo():
    """Muestra un ejemplo de tripletas generadas"""
    print("\n" + "="*60)
    print("EJEMPLO DE TRIPLETAS GENERADAS (primeras 30)")
    print("="*60 + "\n")
    
    contador = 0
    for s, p, o in g:
        if contador < 30:
            print(f"{s}\n  {p}\n    {o}\n")
            contador += 1
        else:
            break


# ============================================================================
# EJECUCIÓN PRINCIPAL
# ============================================================================

if __name__ == "__main__":
    print("="*60)
    print("TRANSFORMACIÓN A RDF CON SCHEMA.ORG")
    print("Consumo de Agua en el Sector Agrícola - Comunidad Valenciana")
    print("="*60)
    
    archivo_entrada = "../pentaho/resultado_proyecto_agua.csv" 
    print(f"\nProcesando archivo: {archivo_entrada}\n")
    
    if not os.path.exists(archivo_entrada):
        print(f"[ERROR] No encuentro el archivo en: {os.path.abspath(archivo_entrada)}")
        print("Asegúrate de que la ruta '../pentaho/resultado_proyecto_agua.csv' es correcta.")
        sys.exit(1)

    total_registros = procesar_csv(archivo_entrada)
    generar_estadisticas()
    
    print("\n" + "="*60)
    print("GUARDANDO GRAFOS EN CARPETA 'outputs'")
    print("="*60)
    
    guardar_grafo('turtle', 'outputs/datos_agricolas')
    guardar_grafo('xml', 'outputs/datos_agricolas')
    guardar_grafo('json-ld', 'outputs/datos_agricolas')
    
    mostrar_ejemplo()
    
    print("\n" + "="*60)
    print("VALIDACIÓN BÁSICA")
    print("="*60)
    
    tipos_esperados = [
        SCHEMA.Place,
        SCHEMA.Product,
        SCHEMA.Event,
        SCHEMA.QuantitativeValue
    ]
    
    print("\nVerificando tipos de recursos:")
    for tipo in tipos_esperados:
        count = len(list(g.subjects(RDF.type, tipo)))
        tipo_nombre = str(tipo).split('/')[-1]
        print(f"   - {tipo_nombre}: {count} recursos")
    
    print("\n" + "="*60)
    print("TRANSFORMACIÓN COMPLETADA CON ÉXITO")
    print("="*60)