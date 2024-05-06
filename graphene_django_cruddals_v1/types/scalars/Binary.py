import graphene
import base64
from graphql.language import ast

class Binary(graphene.Scalar):
    """
    BinaryArray is used to convert a Django BinaryField to the string form
    """

    @staticmethod
    def binary_to_string(value):
        return base64.b64encode(value).decode("utf-8")

    @staticmethod
    def string_to_binary(value):
        return base64.b64decode(value)

    serialize = binary_to_string
    parse_value = string_to_binary

    @classmethod
    def parse_literal(cls, node):
        if isinstance(node, ast.StringValue):
            return cls.string_to_binary(node.value)