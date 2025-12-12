"""
Visualización de datos agrícolas RDF
Genera Mapa de Calor de Costes y Gráficas
"""

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import folium
from folium.plugins import HeatMap  # <--- Necesario para el mapa de calor
from rdflib import Graph, Namespace
import os
import webbrowser
import sys

# Obtener la ruta del directorio donde está el script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
print(f"Directorio de trabajo: {SCRIPT_DIR}\n")

SCHEMA = Namespace("https://schema.org/")
OWL = Namespace("http://www.w3.org/2002/07/owl#")

def cargar_datos_mapa_coste(g):
    """
    Consulta SPARQL modificada para obtener el COSTE
    """
    print("[INFO] Consultando costes y coordenadas (con enlaces Wikidata)...")
    
    query = """
    PREFIX schema: <https://schema.org/>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    
    SELECT ?municipio ?lat ?lon ?wikidataURI (SUM(?coste) as ?total_coste)
    WHERE {
        # 1. Lugares y coordenadas
        ?lugar a schema:Place ;
               schema:name ?municipio_literal ;
               schema:geo ?geo .
        ?geo schema:latitude ?lat ;
             schema:longitude ?lon .

        # 2. Enlace a Wikidata (Opcional pero recomendado)
        OPTIONAL { ?lugar owl:sameAs ?wikidataURI . }

        # 3. Eventos en ese lugar
        ?registro a schema:Event ;
                  schema:location ?lugar .
        
        # 4. FILTRO POR COSTE (El cambio clave)
        ?registro schema:additionalProperty ?prop_coste .
        ?prop_coste schema:name "Coste estimado de producción"@es ;
                    schema:value ?coste .
                   
        BIND(STR(?municipio_literal) as ?municipio)
    }
    GROUP BY ?municipio ?lat ?lon ?wikidataURI
    """
    
    results = g.query(query)
    
    data = []
    for row in results:
        data.append({
            'Municipio': str(row.municipio),
            'Lat': float(row.lat),
            'Lon': float(row.lon),
            'Wikidata': str(row.wikidataURI) if row.wikidataURI else None,
            'Coste': float(row.total_coste)
        })
        
    return pd.DataFrame(data)

def generar_mapa_calor(df):
    """Genera un mapa de calor basado en el coste económico (ESTILO REGIONAL)"""
    if df.empty:
        print("[WARN] No hay datos de coste con coordenadas.")
        return

    # Centrar en la Comunidad Valenciana
    mapa = folium.Map(location=[39.4, -0.6], zoom_start=8, tiles="CartoDB positron")
    
    title_html = '''
             <h3 align="center" style="font-size:16px"><b>Mapa de Calor: Zonas de Inversión Agrícola (€)</b></h3>
             ''' 
    mapa.get_root().html.add_child(folium.Element(title_html))
    
    # 1. CAPA DE CALOR (HEATMAP) AJUSTADA PARA ZONAS GRANDES
    heat_data = df[['Lat', 'Lon', 'Coste']].values.tolist()
    
    HeatMap(heat_data, 
            radius=50,       # <--- MUY IMPORTANTE: Aumentado para cubrir huecos entre pueblos
            blur=35,         # <--- Aumentado para que se mezclen mejor las manchas
            min_opacity=0.3, # <--- Hace que el fondo no sea blanco total, unificando la mancha
            max_zoom=8,      # <--- Ayuda a mantener la proporción al alejar el mapa
            gradient={
                0.2: 'blue',    # Zonas de bajo coste (azul suave)
                0.4: 'cyan',
                0.6: 'lime',    # Zonas medias (verde)
                0.8: 'orange',
                1.0: 'red'      # Puntos calientes (rojo intenso)
            }
           ).add_to(mapa)

    # 2. CAPA INTERACTIVA (CÍRCULOS INVISIBLES)
    # Los mantenemos para que puedas seguir haciendo clic y ver los datos
    for _, row in df.iterrows():
        enlace_wiki = ""
        if row['Wikidata']:
            enlace_wiki = f"""<br><a href="{row['Wikidata']}" target="_blank">Ver en Wikidata ↗</a>"""
            
        popup_html = f"""
        <b>{row['Municipio']}</b><br>
        Coste Total: {row['Coste']:,.2f} €
        {enlace_wiki}
        """
        
        folium.CircleMarker(
            location=[row['Lat'], row['Lon']],
            radius=10, # Un poco más grandes para facilitar el clic
            color=None, # Sin borde
            fill=True,
            fill_color='gray',
            fill_opacity=0, # Totalmente invisibles (solo detectan el clic)
            popup=folium.Popup(popup_html, max_width=200),
            tooltip=f"{row['Municipio']}" # Muestra nombre al pasar el ratón
        ).add_to(mapa)
        
    # GUARDAR EN CARPETA OUTPUTS
    archivo = 'outputs/mapa_calor_costes.html'
    mapa.save(archivo)
    print(f"[OK] Mapa de calor (estilo regional) guardado: {archivo}")
    
    try:
        webbrowser.open('file://' + os.path.realpath(archivo))
    except: pass

def generar_grafica_barras(g):
    """Consulta para gráfica de costes por provincia (TOP 5 grupos) - VERSIÓN MEJORADA"""
    print("Generando gráfica de barras por provincia...")
    
    # Query que usa la jerarquía existente sin addressRegion
    query = """
    PREFIX schema: <https://schema.org/>
    SELECT ?grupo ?provincia (SUM(?coste) as ?total_coste)
    WHERE {
        ?cultivo a schema:Product ; schema:category ?grupo .
        ?reg a schema:Event ; schema:about ?cultivo .
        ?reg schema:location ?municipio .
        
        # Municipio -> Comarca -> Provincia
        ?municipio schema:containedInPlace ?comarca .
        ?comarca schema:containedInPlace ?provincia_uri .
        ?provincia_uri schema:additionalType "provincia"@es ;
                        schema:name ?provincia .
        
        ?reg schema:additionalProperty ?pc .
        ?pc schema:name "Coste estimado de producción"@es ; 
            schema:value ?coste .
    } GROUP BY ?grupo ?provincia ORDER BY ?grupo ?provincia
    """
    
    res = g.query(query)
    df = pd.DataFrame([{
        'Grupo': str(r.grupo), 
        'Provincia': str(r.provincia),
        'Coste': float(r.total_coste)
    } for r in res])
    
    print(f"[INFO] Filas obtenidas: {len(df)}")
    
    if df.empty:
        print("[WARN] No hay datos para generar la gráfica")
        return
    
    # FILTRAR: Solo los 5 grupos con mayor coste total
    coste_por_grupo = df.groupby('Grupo')['Coste'].sum().sort_values(ascending=False)
    top5_grupos = coste_por_grupo.head(5).index.tolist()
    
    print(f"\n[TOP] Top 5 grupos por coste total:")
    for i, (grupo, coste) in enumerate(coste_por_grupo.head(5).items(), 1):
        print(f"   {i}. {grupo}: {coste:,.0f} €")
    
    df_filtrado = df[df['Grupo'].isin(top5_grupos)]
    
    # Pivotear para tener provincias como columnas
    df_pivot = df_filtrado.pivot(index='Grupo', columns='Provincia', values='Coste').fillna(0)
    
    # Ordenar por coste total descendente
    df_pivot['Total'] = df_pivot.sum(axis=1)
    df_pivot = df_pivot.sort_values('Total', ascending=False).drop('Total', axis=1)
    
    # GRÁFICA MEJORADA CON VALORES
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # Colores más distintivos
    colores = {
        'ALICANTE': '#E63946',    # Rojo
        'CASTELLON': '#06FFA5',   # Verde menta
        'VALENCIA': '#1D3557'     # Azul marino
    }
    
    # Asegurar orden de columnas
    orden_provincias = ['ALICANTE', 'CASTELLON', 'VALENCIA']
    columnas_disponibles = [c for c in orden_provincias if c in df_pivot.columns]
    df_pivot = df_pivot[columnas_disponibles]
    
    # Crear barras agrupadas
    bars = df_pivot.plot(
        kind='bar', 
        ax=ax,
        width=0.75,
        color=[colores.get(col, '#999999') for col in df_pivot.columns],
        edgecolor='white',
        linewidth=1.5
    )
    
    # NUEVO: Añadir valores sobre las barras
    for container in ax.containers:
        labels = []
        for bar in container:
            height = bar.get_height()
            if height > 0:
                # Formatear según el tamaño
                if height >= 1e6:
                    label = f'{height/1e6:.1f}M'
                elif height >= 1e3:
                    label = f'{height/1e3:.0f}K'
                else:
                    label = f'{height:.0f}'
                labels.append(label)
            else:
                labels.append('')
        
        ax.bar_label(container, labels=labels, padding=3, fontsize=9, fontweight='bold')
    
    # Formatear eje Y con separadores de miles
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x/1e6)}M' if x >= 1e6 else f'{int(x/1e3)}K'))
    
    # Etiquetas y títulos
    ax.set_ylabel('Coste Estimado de Producción (€)', fontsize=13, fontweight='bold')
    ax.set_xlabel('Grupo de Cultivo', fontsize=13, fontweight='bold')
    ax.set_title('Top 5: Costes de Producción Agrícola por Provincia\nComunidad Valenciana', 
                 fontsize=16, fontweight='bold', pad=20)
    
    # Leyenda mejorada
    ax.legend(
        title='Provincia', 
        title_fontsize=12,
        fontsize=11,
        frameon=True,
        shadow=True,
        loc='upper right',
        fancybox=True
    )
    
    # Rotar etiquetas del eje X
    plt.xticks(rotation=30, ha='right', fontsize=11)
    plt.yticks(fontsize=10)
    
    # Grid sutil
    ax.grid(axis='y', alpha=0.3, linestyle='--', linewidth=0.5)
    ax.set_axisbelow(True)
    
    # NUEVO: Añadir un poco más de espacio arriba para los labels
    y_max = ax.get_ylim()[1]
    ax.set_ylim(0, y_max * 1.15)
    
    # Ajustar layout
    plt.tight_layout()
    
    # Guardar EN CARPETA OUTPUTS
    plt.savefig('outputs/grafica_cultivos_top5.png', dpi=300, bbox_inches='tight', facecolor='white')
    print(f"\n[OK] Gráfica guardada: outputs/grafica_cultivos_top5.png")
    
    # Mostrar estadísticas detalladas
    print(f"\n[RESUMEN] Resumen por provincia (Top 5 grupos):")
    totales_provincia = df_filtrado.groupby('Provincia')['Coste'].sum().sort_values(ascending=False)
    for prov, total in totales_provincia.items():
        porcentaje = (total / totales_provincia.sum()) * 100
        print(f"   {prov}: {total:,.0f} € ({porcentaje:.1f}%)")
    
    print(f"\n[TOTAL] Coste total (Top 5): {totales_provincia.sum():,.0f} €")
    
    # Tabla detallada por grupo y provincia
    print(f"\n[DETALLE] Detalle por grupo:")
    for grupo in df_pivot.index:
        print(f"\n   {grupo}:")
        for provincia in df_pivot.columns:
            valor = df_pivot.loc[grupo, provincia]
            if valor > 0:
                print(f"      - {provincia}: {valor:,.0f} €")

def main():
    # RUTA ACTUALIZADA A OUTPUTS
    archivo = 'outputs/datos_agricolas_enriquecido.ttl'
    
    if not os.path.exists(archivo):
        print(f"[ERROR] Falta el archivo {archivo}.")
        print("   Asegúrate de ejecutar primero el script de enriquecimiento.")
        return

    g = Graph()
    g.parse(archivo, format='turtle')
    print(f"[OK] Grafo cargado: {len(g):,} tripletas")
    
    # 1. Mapa de Calor (Costes) - ACTIVADO
    df_mapa = cargar_datos_mapa_coste(g)
    generar_mapa_calor(df_mapa)
    
    # 2. Gráfica
    generar_grafica_barras(g)

if __name__ == "__main__":
    main()