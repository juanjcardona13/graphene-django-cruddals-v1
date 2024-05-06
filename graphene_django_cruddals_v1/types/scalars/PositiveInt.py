from graphql import GraphQLScalarType, IntValueNode, GraphQLError, ValueNode
from typing import Any

def process_value(value: Any, type: str):
    if value is None:
        return value
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise GraphQLError(f'Value is not a valid {type}: {value}')
    if value < 0:
        raise GraphQLError(f'{type} cannot be less than 0')
    return value

def parse_int_literal(value_node: ValueNode):
    if not isinstance(value_node, IntValueNode):
        raise GraphQLError(f'Can only validate integers as positive integers but got a: {value_node.kind}', nodes=value_node)

    return process_value(value_node.value, 'PositiveInt')

GraphQLPositiveInt = GraphQLScalarType(
    name='PositiveInt',
    description='Integers that will have a value of 0 or more.',
    serialize=lambda value: process_value(value, 'PositiveInt'),
    parse_value=lambda value: process_value(value, 'PositiveInt'),
    parse_literal=parse_int_literal,
    extensions={
        "jsonSchema": {
            "title": 'PositiveInt',
            "type": 'integer',
            "minimum": 0,
        },
    }
)

from graphene.types.scalars import Scalar
class PositiveInt(Scalar):
    """
    Integers that will have a value of 0 or more.
    """
    serialize = lambda value: process_value(value, 'PositiveInt')
    parse_value = lambda value: process_value(value, 'PositiveInt')
    parse_literal = parse_int_literal
