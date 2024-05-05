import graphene
from datetime import timedelta

class Duration(graphene.Scalar):
    """
    Duration fields in Django are stored as timedelta in Python,
    and as a duration in the Database. We will represent them as
    a total number of seconds in GraphQL.
    """

    @staticmethod
    def serialize(dt):
        if isinstance(dt, timedelta):
            return dt.total_seconds()
        else:
            raise Exception(f'Expected a timedelta object, but got {repr(dt)}')

    @staticmethod
    def parse_literal(node):
        if isinstance(node, graphene.IntValue):
            return timedelta(seconds=node.value)
        else:
            raise Exception(f'Cannot represent {node} as timedelta.')

    @staticmethod
    def parse_value(value):
        return timedelta(seconds=value)


"""
    Esta es una implementación por el paquete graphene-django-cud

    Ambas implementaciones son válidas y tienen sus propias ventajas, dependiendo del contexto de uso.
    La primera implementación representa una duración en segundos. Esto es simple y universal, ya que cualquier duración puede ser representada como un número de segundos. Sin embargo, este enfoque puede no ser muy legible o intuitivo para los usuarios que necesiten ingresar o leer duraciones en la interfaz de usuario.
    La segundo implementación representa una duración como un string en el formato "HH:MM:SS", lo cual es mucho más legible e intuitivo para los usuarios humanos. Sin embargo, este formato es un poco más complejo de manejar, ya que requiere una conversión de string a timedelta y viceversa. También puede ser más propenso a errores de entrada, ya que los usuarios podrían ingresar strings mal formados.
    En general, la elección entre estas dos implementaciones depende en gran medida del público objetivo y de cómo se planea usar estos campos de duración en la aplicación.
    Si la mayoría de tus usuarios son humanos que interactúan directamente con la API, y la legibilidad es una prioridad, entonces la implementación "HH:MM:SS" podría ser la mejor opción.
    Si tu API es utilizada principalmente por otras máquinas o servicios, o si prefieres la simplicidad y la universalidad de representar las duraciones como un solo número, entonces la implementación de segundos podría ser la mejor opción.
    Ambas implementaciones son bastante comunes y genéricas en sus respectivos contextos. El enfoque de segundos es más común en la programación en general, mientras que el enfoque "HH:MM:SS" es común en las interfaces de usuario y en las aplicaciones orientadas al usuario.
"""
# import datetime
# import re

# import graphene
# from django.utils import timezone
# from graphql import GraphQLError
# from graphql.language import ast

# class TimeDelta(graphene.Scalar):
#     """
#     TimeDelta is a graphene scalar for rendering and parsing datetime.timedelta objects.
#     """

#     regex = re.compile(r"(?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>\d+?)?")

#     @staticmethod
#     def serialize(timedelta: datetime.timedelta):
#         hours = timedelta.seconds // 3600
#         if timedelta.days > 0:
#             hours += timedelta.days * 24
#         minutes = (timedelta.seconds // 60) % 60
#         seconds = timedelta.seconds % 60

#         return_string = f"{str(hours).zfill(2)}:{str(minutes).zfill(2)}"

#         if seconds:
#             return_string += f":{str(seconds).zfill(2)}"

#         return return_string

#     @staticmethod
#     def parse_literal(node):
#         if isinstance(node, ast.StringValue):
#             return TimeDelta.parse_value(node.value)

#     @staticmethod
#     def parse_value(value):
#         match = TimeDelta.regex.match(value)

#         if not match:
#             raise GraphQLError(f"Error parsing TimeDelta node with format {value}.")

#         days = 0
#         hours = int(match.group("hours"))
#         minutes = int(match.group("minutes"))
#         seconds = match.group("seconds")

#         if hours > 23:
#             days = hours // 24
#             hours = hours % 24

#         if seconds:
#             seconds = int(seconds)

#         return timezone.timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
