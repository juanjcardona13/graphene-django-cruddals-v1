from graphql import StringValueNode, GraphQLError, ValueNode, print_ast
from typing import Any
import re


from graphene.types.scalars import Scalar
class Email(Scalar):
    """
    A field whose value conforms to the standard 
    internet email address format as specified in 
    HTML Spec: https://html.spec.whatwg.org/multipage/input.html#valid-e-mail-address.
    """

    @staticmethod
    def validate(value: Any, ast: Any = None):
        EMAIL_ADDRESS_REGEX = re.compile(r'^[a-zA-Z0-9.!#$%&\'*+\/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$')

        if not isinstance(value, str):
            raise GraphQLError(f'Value is not string: {value}', nodes=ast)

        if not EMAIL_ADDRESS_REGEX.match(value):
            raise GraphQLError(f'Value is not a valid email address: {value}', nodes=ast)

        return value
    
    serialize = validate
    parse_value = validate

    @staticmethod
    def parse_literal(value_node: ValueNode):
        if not isinstance(value_node, StringValueNode):
            raise GraphQLError(
                f'Can only validate strings as email addresses but got a: {print_ast(value_node)}',
                value_node
            )

        return Email.validate(value_node.value, value_node)

