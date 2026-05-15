from django import template

register = template.Library()


CLOUDINARY_UPLOAD_MARKER = '/image/upload/'


@register.simple_tag
def logo_url(logo_field, width=0):
    """
    URL optimizada del logo. Si el storage es Cloudinary, inserta
    transformaciones (f_auto,q_auto,w_N) para que el navegador reciba
    una versión pequeña y comprimida. Si no es Cloudinary devuelve la URL original.

    Uso:
        {% logo_url config_general.logo 64 %}

    Si width es 0 o None se omite el redimensionado pero igual se aplica
    f_auto,q_auto cuando es Cloudinary.
    """
    if not logo_field:
        return ''
    try:
        url = logo_field.url
    except Exception:
        return ''

    if CLOUDINARY_UPLOAD_MARKER not in url:
        return url

    parts = []
    parts.append('f_auto')
    parts.append('q_auto')
    try:
        w = int(width)
        if w > 0:
            parts.append(f'w_{w}')
            parts.append('c_limit')
            parts.append('dpr_auto')
    except (TypeError, ValueError):
        pass

    transformation = ','.join(parts)
    return url.replace(CLOUDINARY_UPLOAD_MARKER, f'{CLOUDINARY_UPLOAD_MARKER}{transformation}/', 1)
