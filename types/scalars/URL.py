from graphql import GraphQLScalarType, StringValueNode, GraphQLError, ValueNode
from typing import Any
from urllib.parse import urlparse

def validate(value: Any):
    if value is None:
        return value
    
    try:
        from django.core.exceptions import ValidationError
        from django.core.validators import URLValidator
        validator = URLValidator()
    except Exception as e:
        url = urlparse(str(value))
        if url.scheme and url.netloc:
            return url.geturl()
        else:
            raise GraphQLError(f'Value is not a valid URL: {value}')

    try:
        validator(value)
        return value
    except ValidationError:
        raise GraphQLError(f'Value is not a valid URL: {value}')

def parse_url_literal(value_node: ValueNode):
    if not isinstance(value_node, StringValueNode):
        raise GraphQLError(f'Can only validate strings as URLs but got a: {value_node.kind}', nodes=value_node)

    return validate(value_node.value)

GraphQLURL = GraphQLScalarType(
    name='URL',
    description='A field whose value conforms to the standard URL format as specified in RFC3986: https://www.ietf.org/rfc/rfc3986.txt.',
    serialize=validate,
    parse_value=validate,
    parse_literal=parse_url_literal,
    extensions={
        "codegenScalarType": 'URL | string',
        "jsonSchema": {
            "type": 'string',
            "format": 'uri',
        },
    }
)

from graphene.types.scalars import Scalar
class URL(Scalar):
    """
    A field whose value conforms to the standard URL format as specified in RFC3986: https://www.ietf.org/rfc/rfc3986.txt.
    """
    serialize = validate
    parse_value = validate
    parse_literal = parse_url_literal
