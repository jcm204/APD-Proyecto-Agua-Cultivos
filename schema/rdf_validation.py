"""
Validación y consultas SPARQL sobre los datos RDF generados
"""

from rdflib import Graph, Namespace, Literal 
from rdflib.namespace import RDF, RDFS
import pandas as pd
import os
import sys

# Obtener la ruta del directorio donde está el script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Cambiar al directorio del script
os.chdir(SCRIPT_DIR)

print(f"Directorio de trabajo: {SCRIPT_DIR}\n")

# Ahora todos los archivos se guardarán/leerán desde aquí

SCHEMA = Namespace("https://schema.org/")
EX = Namespace("http://example.org/agricultura/")

class ValidadorRDF:
    """Clase para validar y consultar datos RDF"""
    
    def __init__(self, archivo_rdf):
        self.g = Graph()
        # Intentar cargar el archivo
        print(f"Cargando grafo desde: {archivo_rdf}...")
        self.g.parse(archivo_rdf, format='turtle')
        self.g.bind("schema", SCHEMA)
        self.g.bind("ex", EX)
        
    def validacion_basica(self):
        """Realiza validaciones básicas del grafo"""
        print("\n" + "="*60)
        print("VALIDACION BASICA DEL GRAFO RDF")
        print("="*60)
        
        # 1. Total de tripletas
        total = len(self.g)
        print(f"\nTotal de tripletas: {total:,}")
        
        if total == 0:
            print("[ERROR] El grafo está vacío")
            return False
        
        # 2. Verificar clases
        clases_esperadas = {
            'Place': SCHEMA.Place,
            'Product': SCHEMA.Product,
            'Event': SCHEMA.Event,
            'QuantitativeValue': SCHEMA.QuantitativeValue,
            'MonetaryAmount': SCHEMA.MonetaryAmount 
        }
        
        print(f"\nVerificación de clases:")
        todo_ok = True
        for nombre, clase in clases_esperadas.items():
            count = len(list(self.g.subjects(RDF.type, clase)))
            status = "[OK]" if count > 0 else "[ERROR]"
            print(f"   {status} {nombre}: {count:,} instancias")
            if count == 0:
                todo_ok = False
        
        # 3. Verificar propiedades esenciales
        propiedades_esperadas = [
            SCHEMA.name,
            SCHEMA.location,
            SCHEMA.value,
            SCHEMA.unitCode
        ]
        
        print(f"\nVerificación de propiedades:")
        for prop in propiedades_esperadas:
            count = len(list(self.g.subject_objects(prop)))
            status = "[OK]" if count > 0 else "[ERROR]"
            prop_name = str(prop).split('/')[-1]
            print(f"   {status} schema:{prop_name}: {count:,} usos")
            if count == 0:
                todo_ok = False
        
        # 4. Verificar integridad de datos numéricos
        print(f"\nVerificación de datos numéricos:")
        
        valores_negativos = 0
        for s in self.g.subjects(RDF.type, SCHEMA.QuantitativeValue):
            for valor in self.g.objects(s, SCHEMA.value):
                try:
                    if float(valor) < 0:
                        valores_negativos += 1
                except ValueError:
                    pass
        
        if valores_negativos == 0:
            print(f"   [OK] No hay valores negativos")
        else:
            print(f"   [!] Valores negativos encontrados: {valores_negativos}")
        
        return todo_ok
    
    def consulta_sparql(self, nombre, query):
        """Ejecuta una consulta SPARQL y muestra resultados"""
        print(f"\n{'='*60}")
        print(f"CONSULTA: {nombre}")
        print(f"{'='*60}")
        
        try:
            resultados = self.g.query(query)
            
            if len(resultados) == 0:
                print("[!] No se encontraron resultados")
                return None
            
            # Convertir a DataFrame para mejor visualización
            datos = []
            for row in resultados:
                datos.append([str(val) if val else "" for val in row])
            
            if datos:
                columnas = [str(var) for var in resultados.vars]
                df = pd.DataFrame(datos, columns=columnas)
                print(f"\nResultados ({len(df)} filas):\n")
                print(df.to_string(index=False))
                return df
            
        except Exception as e:
            print(f"[ERROR] Error en consulta: {e}")
            return None
    
    def ejecutar_consultas_ejemplo(self):
        """Ejecuta un conjunto de consultas de ejemplo"""
        
        print("\n" + "="*60)
        print("CONSULTAS SPARQL DE EJEMPLO")
        print("="*60)
        
        # Consulta 1: Top 10 municipios por superficie cultivada
        query1 = """
        PREFIX schema: <https://schema.org/>
        PREFIX ex: <http://example.org/agricultura/>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        
        SELECT ?municipio (SUM(?superficie) as ?total_superficie)
        WHERE {
          ?lugar a schema:Place ;
                 schema:additionalType "municipio"@es ;
                 schema:name ?municipio .
          
          ?registro a schema:Event ;
                    schema:location ?lugar ;
                    schema:area ?area_node .
          
          ?area_node schema:value ?superficie .
        }
        GROUP BY ?municipio
        ORDER BY DESC(?total_superficie)
        LIMIT 10
        """
        
        self.consulta_sparql("Consulta 1: Top 10 Municipios por Superficie Cultivada", query1)
        
        # Consulta 2: Consumo de agua por tipo de cultivo
        query2 = """
        PREFIX schema: <https://schema.org/>
        PREFIX ex: <http://example.org/agricultura/>
        
        SELECT ?grupo_cultivo (SUM(?consumo) as ?consumo_total) (COUNT(?registro) as ?num_registros)
        WHERE {
          ?cultivo a schema:Product ;
                   schema:category ?grupo_cultivo .
          
          ?registro a schema:Event ;
                    schema:about ?cultivo .
          
          ?registro schema:additionalProperty ?consumo_node .
          ?consumo_node schema:name "Consumo estimado de agua"@es ;
                        schema:value ?consumo .
        }
        GROUP BY ?grupo_cultivo
        ORDER BY DESC(?consumo_total)
        LIMIT 10
        """
        
        self.consulta_sparql("Consulta 2: Consumo de Agua por Grupo de Cultivo", query2)
        
        # Consulta 3: Estadísticas por comarca en Valencia
        query3 = """
        PREFIX schema: <https://schema.org/>
        
        SELECT ?comarca 
               (COUNT(DISTINCT ?municipio) as ?num_municipios)
               (SUM(?superficie) as ?superficie_total)
               (AVG(?dotacion) as ?dotacion_media)
        WHERE {
          ?prov a schema:Place ;
                schema:name "VALENCIA" .
          
          ?comarca a schema:Place ;
                   schema:additionalType "comarca"@es ;
                   schema:name ?nombre_comarca ;
                   schema:containedInPlace ?prov .
          
          ?municipio schema:containedInPlace ?comarca .
          
          ?registro a schema:Event ;
                    schema:location ?municipio ;
                    schema:area ?area_node .
          
          ?area_node schema:value ?superficie .
          
          ?registro schema:additionalProperty ?dotacion_node .
          ?dotacion_node schema:name "Dotación de agua"@es ;
                         schema:value ?dotacion .
          
          BIND(STR(?nombre_comarca) as ?comarca)
        }
        GROUP BY ?comarca
        ORDER BY DESC(?superficie_total)
        LIMIT 10
        """
        
        self.consulta_sparql("Consulta 3: Estadísticas por Comarca (Valencia)", query3)

    
    def generar_reporte_completo(self):
        """Genera un reporte completo de validación"""
        print("\n" + "="*70)
        print(" "*15 + "REPORTE DE VALIDACION RDF")
        print("="*70)
        
        # Validación básica
        validacion_ok = self.validacion_basica()
        
        # Estadísticas adicionales
        print(f"\n" + "="*60)
        print("ESTADISTICAS DETALLADAS")
        print("="*60)
        
        # Contar provincias
        provincias = len(list(self.g.subjects(
            SCHEMA.additionalType, 
            Literal("provincia", lang="es")
        )))
        print(f"\n   Provincias: {provincias}")
        
        # Contar comarcas
        comarcas = len(list(self.g.subjects(
            SCHEMA.additionalType,
            Literal("comarca", lang="es")
        )))
        print(f"   Comarcas: {comarcas}")
        
        # Contar municipios
        municipios = len(list(self.g.subjects(
            SCHEMA.additionalType,
            Literal("municipio", lang="es")
        )))
        print(f"   Municipios: {municipios}")
        
        # Contar cultivos únicos
        cultivos = len(set(self.g.subjects(RDF.type, SCHEMA.Product)))
        print(f"   Cultivos únicos: {cultivos}")
        
        # Contar registros
        registros = len(list(self.g.subjects(RDF.type, SCHEMA.Event)))
        print(f"   Registros agrícolas: {registros}")
        
        # Consultas
        self.ejecutar_consultas_ejemplo()
        
        # Resultado final
        print("\n" + "="*70)
        if validacion_ok:
            print("VALIDACION COMPLETADA CON EXITO")
        else:
            print("VALIDACION COMPLETADA CON ADVERTENCIAS")
        print("="*70 + "\n")


def main():
    """Función principal"""
    
    # Determinar archivo a validar
    if len(sys.argv) > 1:
        archivo = sys.argv[1]
    else:
        # RUTA CORRECTA: outputs/datos_agricolas.ttl
        archivo = 'outputs/datos_agricolas.ttl'
    
    print("="*70)
    print(" "*10 + "VALIDADOR DE DATOS RDF - PROYECTO AGUA AGRICOLA")
    print("="*70)
    print(f"\nArchivo: {archivo}\n")
    
    try:
        validador = ValidadorRDF(archivo)
        validador.generar_reporte_completo()
    except FileNotFoundError:
        print(f"[ERROR] No se encuentra el archivo '{archivo}'")
        print("   Verifica que has ejecutado primero el script de transformación.")
        print("   Uso: python validacion_rdf.py [ruta/al/archivo.ttl]")
    except Exception as e:
        print(f"[ERROR] Error inesperado: {e}")


if __name__ == "__main__":
    main()