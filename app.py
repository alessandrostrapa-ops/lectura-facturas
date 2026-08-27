import streamlit as st
import pandas as pd
from PIL import Image
from google import genai
import io
import time

from streamlit_gsheets import GSheetsConnection

# --- SISTEMA DE LOGIN (SEGURIDAD) ---
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False

if not st.session_state['autenticado']:
    st.title("🔒 Acceso Restringido")
    clave_ingresada = st.text_input("Ingresá la contraseña para acceder al sistema:", type="password")
    
    if st.button("Ingresar"):
        if clave_ingresada == "kiosko2026": 
            st.session_state['autenticado'] = True
            st.success("Acceso concedido. Cargando sistema...")
            time.sleep(1)
            st.rerun() 
        else:
            st.error("Contraseña incorrecta.")
    
    st.stop() 

# ==========================================
# A PARTIR DE ACÁ, ES TU CÓDIGO PRINCIPAL
# ==========================================

# Configuración de Google Gemini
cliente_ia = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])
modelo_vision = "gemini-3.6-flash"

# Configuración de base de datos (Google Sheets)
conn = st.connection("gsheets", type=GSheetsConnection)

st.title("Sistema de Lectura de Facturas 🧾")

# --- BARRA LATERAL (MENU Y SOBRE MÍ) ---
with st.sidebar:
    st.image("https://media.licdn.com/dms/image/v2/D5603AQFUOXNVUIczVg/profile-displayphoto-crop_800_800/B56Zo6ewwaJwAI-/0/1761917734504?e=1789603200&v=beta&t=NM6BsGpVZToEgwR4asKlBL4f4E-8VmvBDpdkq9HNU3c", width=100) 
    st.header("👨‍💻 Sobre el Desarrollador")
    st.markdown("""
    **Sistema de Gestión Kiosko v1.0**
    
    Desarrollado por **Robert Alessandro Strapasson**.
    
    Herramienta automatizada con Inteligencia Artificial para conciliación de stock y precios.
    
    📫 **Contacto:**
    - [Email](mailto:robertstrapasson@gmail.com)
    - [GitHub](https://github.com/alessandrostrapa-ops)
    - [LinkedIn](https://www.linkedin.com/in/robert-strapasson-936747311/)
    """)
    
    st.divider()
    st.caption("Hecho con ❤️ y Python")

# --- MEMORIA DEL DASHBOARD ---
if 'tabla_maestra' not in st.session_state:
    st.session_state['tabla_maestra'] = pd.DataFrame(columns=[
        'Proveedor', 'Producto', 'Unidades por Bulto', 'Costo Unitario', 'Precio con IVA', 'Precio Venta (Final)'
    ])

if 'factura_temporal' not in st.session_state:
    st.session_state['factura_temporal'] = None

# --- PASO 1: CARGA Y EXTRACCIÓN ---
st.subheader("Paso 1: Cargar Factura")

# NUEVO: Input para el proveedor
nombre_proveedor = st.text_input("🏢 Nombre del Proveedor (Ej: Arcor, Coca-Cola, etc.)")

archivo_subido = st.file_uploader("Elegí una imagen de tu factura", type=["png", "jpg", "jpeg"])

if archivo_subido is not None:
    # NUEVO: Control para obligar a poner el proveedor
    if nombre_proveedor.strip() == "":
        st.warning("⚠️ Por favor, escribí el nombre del proveedor arriba antes de continuar.")
    else:
        with st.expander("Ver imagen de la factura"):
            st.image(Image.open(archivo_subido), caption="Factura actual", use_container_width=True)
        
        if st.button("Extraer datos con IA"):
            with st.spinner('Analizando factura...'):
                try:
                    # 1. MODIFICAMOS LA INSTRUCCIÓN: Le damos la orden estricta del formato de número
                    instruccion = """
                    Analiza esta factura. Extrae los productos y devuelve la información estrictamente con este formato:
                    Producto | Precio Costo del Bulto
                    No agregues texto adicional, cantidades compradas, ni introducciones, solo Producto y Precio separados por la barra vertical (|).
                    REGLA VITAL: El precio debe ser un número puro, usando SOLO un punto (.) para los decimales. No uses separador de miles, ni comas, ni signos de pesos ($). Ejemplo correcto: 1865.09
                    """
                    
                    for intento in range(2):
                        try:
                            respuesta = cliente_ia.models.generate_content(
                                model=modelo_vision,
                                contents=[instruccion, Image.open(archivo_subido)]
                            )
                            texto_extraido = respuesta.text
                            break
                        except Exception as e:
                            if "503" in str(e) and intento == 0:
                                time.sleep(2)
                                continue
                            else:
                                raise e

                    lineas = texto_extraido.strip().split('\n')
                    datos = [linea.split('|') for linea in lineas if '|' in linea]
                    if "Producto" in datos[0][0]:
                        datos = datos[1:] 
                        
                    df_temp = pd.DataFrame(datos, columns=['Producto', 'Precio Costo del Bulto'])
                    df_temp['Producto'] = df_temp['Producto'].str.strip()
                    
                    # 2. LIMPIEZA DE CÓDIGO: Por si la IA se rebela y mete un signo peso o un espacio raro
                    df_temp['Precio Costo del Bulto'] = df_temp['Precio Costo del Bulto'].str.replace('$', '', regex=False).str.strip().astype(float)
                    
                    df_temp['Unidades por Bulto'] = 1
                    
                    st.session_state['factura_temporal'] = df_temp
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Hubo un error de conexión con la IA: {e}")

# --- PASO 2: SIMULADOR Y REVISIÓN MANUAL ---
if st.session_state['factura_temporal'] is not None:
    st.divider()
    st.subheader("Paso 2: Simulador de Precios ✏️")
    
    col1, col2 = st.columns(2)
    with col1:
        porcentaje_iva = st.number_input("IVA de esta factura (%)", min_value=0.0, value=21.0, step=1.0)
    with col2:
        porcentaje_ganancia = st.number_input("Ganancia para esta factura (%)", min_value=0.0, value=90.0, step=5.0)
    
    st.info("Editá la columna 'Unidades por Bulto'. Los precios finales de abajo se actualizarán solos.")
    
    df_editado = st.data_editor(
        st.session_state['factura_temporal'],
        column_config={
            "Unidades por Bulto": st.column_config.NumberColumn("Unidades por Bulto", min_value=1, step=1)
        },
        use_container_width=True,
        hide_index=True
    )
    
    df_calculado = df_editado.copy()
    df_calculado['Costo Unitario'] = df_calculado['Precio Costo del Bulto'] / df_calculado['Unidades por Bulto']
    df_calculado['Precio con IVA'] = df_calculado['Costo Unitario'] * (1 + porcentaje_iva / 100)
    df_calculado['Precio Venta (Final)'] = df_calculado['Precio con IVA'] * (1 + porcentaje_ganancia / 100)
    df_calculado = df_calculado.round(2)
    
    # NUEVO: Insertamos el nombre del proveedor en la tabla
    df_calculado.insert(0, 'Proveedor', nombre_proveedor)
    
    st.write("### Vista Previa de Precios (No guardado aún)")
    df_vista_previa = df_calculado[['Proveedor', 'Producto', 'Unidades por Bulto', 'Costo Unitario', 'Precio con IVA', 'Precio Venta (Final)']]
    st.dataframe(df_vista_previa, use_container_width=True)
    
    # --- PASO 3: ACCIONES MANUALES ---
    st.write("¿Qué querés hacer con esta boleta?")
    col_btn1, col_btn2 = st.columns(2)
    
    with col_btn1:
        if st.button("✅ Agregar boleta al Reporte de Jefes", use_container_width=True):
            if st.session_state['tabla_maestra'].empty:
                st.session_state['tabla_maestra'] = df_vista_previa
            else:
                st.session_state['tabla_maestra'] = pd.concat([st.session_state['tabla_maestra'], df_vista_previa], ignore_index=True)
            
            # NUEVO: Sincronizar con Google Sheets en la nube
            conn.update(data=st.session_state['tabla_maestra'])

            st.session_state['factura_temporal'] = None
            st.toast('¡Boleta agregada al reporte diario!', icon='✅')
            st.rerun()

    with col_btn2:
        if st.button("🗑️ Descartar prueba (Limpiar)", use_container_width=True):
            st.session_state['factura_temporal'] = None
            st.rerun()

# --- SECCIÓN DEL REPORTE FINAL ---
st.divider()
st.subheader("📊 Reporte Acumulado del Día")

if not st.session_state['tabla_maestra'].empty:
    st.session_state['tabla_maestra'] = st.data_editor(st.session_state['tabla_maestra'], use_container_width=True, hide_index=True)
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        st.session_state['tabla_maestra'].to_excel(writer, index=False, sheet_name='Facturacion del Dia')
    
    st.download_button(
        label="📥 Descargar Excel Final para los Jefes",
        data=buffer.getvalue(),
        file_name="Reporte_Diario_Kiosko.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    if st.button("Limpiar reporte (Cerrar día)"):
        # NUEVO: Efecto de celebración
        st.balloons()
        time.sleep(2) # Pausa para ver la animación antes de borrar todo
        # NUEVO: Vaciamos la memoria y vaciamos el Google Sheet
        # Vaciamos la memoria manteniendo las columnas, y vaciamos el Google Sheet
        df_vacio = pd.DataFrame(columns=[
            'Proveedor', 'Producto', 'Unidades por Bulto', 'Costo Unitario', 'Precio con IVA', 'Precio Venta (Final)'
        ])
        
        st.session_state['tabla_maestra'] = df_vacio
        conn.update(data=st.session_state['tabla_maestra'])
        
        st.rerun()
else:
    st.info("El reporte para enviar a los jefes está vacío.")