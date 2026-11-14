# Seguridad

## Qué protege Centinela y qué no

Centinela reduce el riesgo de que un mensaje manipule a un asistente de IA o a la persona que lo lee. No es una garantía: un mensaje nuevo o ingenioso puede pasar el guardia. Por eso el diseño pone las decisiones delicadas en código y, ante la duda, se las deja a una persona.

## Cómo avisar de un problema

Si encuentras una forma de saltarte el guardia o el clasificador, o cualquier otro problema de seguridad:

1. **No abras un issue público** ni publiques el mensaje que lo logra.
2. Usa el aviso privado de GitHub: pestaña **Security** del repositorio, opción **Report a vulnerability**.
3. Cuenta qué versión usaste, qué detector estaba activo y qué esperabas que pasara.

Respondemos lo antes posible. Cuando el problema esté corregido, sumamos un caso al banco de pruebas para que no vuelva a pasar, con tu crédito si lo quieres.

## Uso responsable

- El banco de pruebas contiene mensajes de ataque porque hacen falta para medir defensas. Son traducciones de ataques ya públicos y ejemplos genéricos, no herramientas listas para atacar un sistema concreto.
- No uses Centinela ni sus datos para probar sistemas de terceros sin permiso escrito.
- Los ejemplos no deben contener datos personales reales.
