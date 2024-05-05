from graphql import GraphQLScalarType, StringValueNode, GraphQLError, ValueNode, print_ast
from typing import Any
from .IPv4 import IPV4_REGEX
from .IPv6 import IPV6_REGEX

def validate(value: Any, ast: Any = None):
    if not value:
        return value
    
    if not isinstance(value, str):
        raise GraphQLError(f'Value is not string: {value}', nodes=ast)

    if not IPV4_REGEX.match(value) and not IPV6_REGEX.match(value):
        raise GraphQLError(f'Value is not a valid IPv4 or IPv6 address: {value}', nodes=ast)

    return value

def parse_ip_literal(value_node: ValueNode):
    if not isinstance(value_node, StringValueNode):
        raise GraphQLError(f'Can only validate strings as IP addresses but got a: {print_ast(value_node)}', nodes=value_node)

    return validate(value_node.value, value_node)

GraphQLIP = GraphQLScalarType(
    name='IP',
    description='A field whose value is either an IPv4 or IPv6 address: https://en.wikipedia.org/wiki/IP_address.',
    serialize=validate,
    parse_value=validate,
    parse_literal=parse_ip_literal,
    extensions={
        "jsonSchema": {
            "title": 'IP',
            "oneOf": [
                {
                    type: 'string',
                    format: 'ipv4',
                },
                {
                    type: 'string',
                    format: 'ipv6',
                },
            ],
        },
    }
)

from graphene.types.scalars import Scalar
class IP(Scalar):
    """
    A field whose value is either an IPv4 or IPv6 address: https://en.wikipedia.org/wiki/IP_address.
    """
    serialize = validate
    parse_value = validate
    parse_literal = parse_ip_literal
