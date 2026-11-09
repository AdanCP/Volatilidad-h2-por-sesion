# Reglas de trabajo del proyecto

1. **Lo que ya funciona no se modifica.** Al agregar una funcionalidad nueva o hacer un cambio puntual, el resto de la app, el motor, el bot y la guía quedan como están.
2. **Solo se cambia algo existente en dos casos:**
   - Claude avisa de forma expresa, antes de hacerlo, que para lograr lo pedido hay que cambiar algo que ya existe (qué y por qué), y espera la confirmación.
   - El usuario lo pide específicamente.
3. **Teorizar primero.** Cuando el usuario dice «teoricemos», se discute y se espera su confirmación antes de programar.
4. **Después de cada cambio** se reenvían los archivos modificados.
5. **Lo que no se pudo probar** (pantalla de Streamlit, compilación en MetaEditor, impresión a PDF en el navegador) se dice claramente, porque lo verifica el usuario.
