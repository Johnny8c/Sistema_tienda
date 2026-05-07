import re
from django.core.exceptions import ValidationError


class ComplexityValidator:
    """Exige al menos: 1 mayúscula, 1 minúscula y 1 número."""

    def validate(self, password, user=None):
        errores = []
        if not re.search(r'[A-Z]', password):
            errores.append('una letra mayúscula')
        if not re.search(r'[a-z]', password):
            errores.append('una letra minúscula')
        if not re.search(r'[0-9]', password):
            errores.append('un número')
        if errores:
            raise ValidationError(
                'La contraseña debe contener al menos: ' + ', '.join(errores) + '.',
                code='password_no_complexity',
            )

    def get_help_text(self):
        return 'Debe contener al menos una mayúscula, una minúscula y un número.'
