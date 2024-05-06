
import graphene
from graphene.types.generic import GenericScalar
from enum import Enum



class IntOrAll(GenericScalar):
    class Meta:
        description = "The page size can be int or 'All'"

class SearchValues(GenericScalar):
    class Meta:
        description = "The searchValue can be of any type"

class FieldFilterInput(graphene.InputObjectType):
    field = graphene.String(required=True, description="Field or subfield of the model to search with Django's ORM.")
    filter = graphene.String(default_value="exact", description="Django Lookups")

class AdvancedSearchInput(graphene.InputObjectType):
    fields_and_filters = graphene.List(graphene.NonNull(FieldFilterInput), required=True)
    search_values = graphene.List(graphene.NonNull(SearchValues), required=True)

class PaginationInterface(graphene.Interface):
    total = graphene.Int()
    page = graphene.Int()
    pages = graphene.Int()
    has_next = graphene.Boolean()
    has_prev = graphene.Boolean()
    index_start_obj = graphene.Int()
    index_end_obj = graphene.Int()

class PaginatedInput(graphene.InputObjectType):
    page = graphene.InputField(type_=graphene.Int, default_value=1)
    page_size = graphene.InputField(type_=IntOrAll, default_value="All")




class TypesMutation(Enum):
    CREATE = "create"
    UPDATE = "update"
    CREATE_UPDATE = "create_update"


class CruddalsRelationField:
    """Return params necessary for convert field to relation field"""

    def __init__(self, prefix="", suffix=""):
        self.prefix = prefix
        self.suffix = suffix
