from graphql import GraphQLScalarType, StringValueNode, GraphQLError, ValueNode, print_ast
from typing import Any
import re

IPV4_REGEX = re.compile(r'^(?:(?:(?:0?0?[0-9]|0?[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])\.){3}(?:0?0?[0-9]|0?[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])(?:\/(?:[0-9]|[1-2][0-9]|3[0-2]))?)$')

def validate(value: Any, ast: Any = None):
    if not value:
        return value
    
    if not isinstance(value, str):
        raise GraphQLError(f'Value is not string: {value}', nodes=ast)

    if not IPV4_REGEX.match(value):
        raise GraphQLError(f'Value is not a valid IPv4 address: {value}', nodes=ast)

    return value

def parse_ipv4_literal(value_node: ValueNode):
    if not isinstance(value_node, StringValueNode):
        raise GraphQLError(f'Can only validate strings as IPv4 addresses but got a: {print_ast(value_node)}', nodes=value_node)

    return validate(value_node.value, value_node)

GraphQLIPv4 = GraphQLScalarType(
    name='IPv4',
    description='A field whose value is a IPv4 address: https://en.wikipedia.org/wiki/IPv4.',
    serialize=validate,
    parse_value=validate,
    parse_literal=parse_ipv4_literal,
    extensions={
        "jsonSchema": {
            "type": 'string',
            "format": 'ipv4',
        },
    }
)

from graphene.types.scalars import Scalar
class IPv4(Scalar):
    """
    A field whose value is a IPv4 address: https://en.wikipedia.org/wiki/IPv4.
    """
    serialize = validate
    parse_value = validate
    parse_literal = parse_ipv4_literal
