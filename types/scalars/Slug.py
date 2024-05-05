from graphql import GraphQLScalarType, StringValueNode, GraphQLError, ValueNode
from typing import Any
import re

SLUG_REGEX = re.compile(r'^[-a-zA-Z0-9_]+\Z')

def validate(value: Any, ast: Any = None):
    if not isinstance(value, str):
        raise GraphQLError(f'Value is not string: {value}', nodes=ast)

    if not SLUG_REGEX.match(value):
        raise GraphQLError(f'Value is not a valid slug: {value}', nodes=ast)

    return value

def parse_url_literal(value_node: ValueNode):
    if not isinstance(value_node, StringValueNode):
        raise GraphQLError(f'Can only validate strings as Slugs but got a: {value_node.kind}', nodes=value_node)

    return validate(value_node.value)

GraphQLSlug = GraphQLScalarType(
    name='Slug',
    description='Slug is a newspaper term. A slug is a short label for something, containing only letters, numbers, underscores or hyphens. They’re generally used in URLs.',
    serialize=validate,
    parse_value=validate,
    parse_literal=parse_url_literal,
    extensions={
        "codegenScalarType": 'Slug | string',
        "jsonSchema": {
            "type": 'string',
            "format": 'uri',
        },
    }
)

from graphene.types.scalars import Scalar
class Slug(Scalar):
    """
    Slug is a newspaper term. A slug is a short label for something, containing only letters, numbers, underscores or hyphens. They’re generally used in URLs.
    """
    serialize = validate
    parse_value = validate
    parse_literal = parse_url_literal
