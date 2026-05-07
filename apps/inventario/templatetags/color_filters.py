from django import template

register = template.Library()

COLORES_ES = {
    'blanco': '#FFFFFF', 'negro': '#000000', 'gris': '#9CA3AF', 'plata': '#C0C0C0',
    'rojo': '#DC2626', 'rosa': '#F472B6', 'rosado': '#F9A8D4',
    'naranja': '#F97316', 'naranjado': '#F97316', 'durazno': '#FBBF24',
    'amarillo': '#FACC15', 'mostaza': '#CA8A04',
    'verde': '#16A34A', 'verde menta': '#86EFAC', 'verde militar': '#4D7C0F',
    'verde oliva': '#65A30D', 'turquesa': '#06B6D4',
    'azul': '#2563EB', 'azul oscuro': '#1E40AF', 'azul claro': '#60A5FA',
    'azul desgastado': '#3B82F6', 'celeste': '#7DD3FC', 'marino': '#172554',
    'morado': '#9333EA', 'violeta': '#8B5CF6', 'lila': '#C4B5FD',
    'purpura': '#7C3AED', 'púrpura': '#7C3AED',
    'cafe': '#92400E', 'café': '#92400E', 'marron': '#78350F', 'marrón': '#78350F',
    'chocolate': '#5C3317',
    'beige': '#E7DCC0', 'crema': '#FFFDD0', 'hueso': '#F5F5DC', 'arena': '#D4B996',
    'coral': '#FB7185', 'salmon': '#FCA5A5', 'salmón': '#FCA5A5',
    'dorado': '#FBBF24', 'oro': '#D4AF37', 'bronce': '#CD7F32',
}


@register.filter(name='color_css')
def color_css(nombre):
    """Traduce un nombre de color en español a su valor CSS (hex).
    Si el nombre ya es un color CSS válido en inglés (ej. 'coral', 'beige'),
    lo retorna tal cual. Si está vacío, devuelve un gris neutro."""
    if not nombre:
        return '#94A3B8'
    k = nombre.lower().strip()
    return COLORES_ES.get(k, k)
