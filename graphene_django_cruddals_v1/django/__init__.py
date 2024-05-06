import importlib
from django.db.models.fields import Field

def get_field_classes(module_name):
    module = importlib.import_module(module_name)
    return {name: cls for name, cls in module.__dict__.items() if isinstance(cls, type) and issubclass(cls, Field)}

# Obtén los tipos de campo de django.db.models
django_fields = get_field_classes('django.db.models')

# Obtén los tipos de campo de django.contrib.postgres.fields
try:
    # Postgres fields are only available in Django with psycopg2 installed
    # and we cannot have psycopg2 on PyPy
    postgres_fields = get_field_classes('django.contrib.postgres.fields')
except ImportError:
    postgres_fields = {}

# Combina ambos en un solo diccionario
all_fields = {**django_fields, **postgres_fields} # 

lookups = {}
for k, v in all_fields.items():
    # print(k, v)
    lookups[k] = v.get_lookups()




#* Field types
###===== AutoField       => graphene.ID
###===== BigAutoField    => graphene.ID
###===== SmallAutoField  => graphene.ID
###===== CharField       => graphene.String
###===== TextField       => graphene.String
###===== IntegerField    => graphene.Int
###===== BooleanField    => graphene.Boolean
###===== BigIntegerField => graphene.BigInt
###===== DateField       => graphene.Date
###===== TimeField       => graphene.Time
###===== DateTimeField   => graphene.DateTime
###===== DecimalField    => graphene.Decimal
###===== FloatField      => graphene.Float
###===== JSONField       => graphene.JSONString
###===== UUIDField       => graphene.UUID
###===== FileField       => graphene_file_upload.Upload
###===== ImageField      => graphene_file_upload.Upload
###===== EmailField            => cruddals.Email
###===== GenericIPAddressField => cruddals.IPv4
###=====! IPAddressField       => cruddals.IP (No esta en la doc de Django)
###=====! DurationField        => cruddals.Duration (Django y graphql-scalars toman diferentes definiciones hay que investigar mas)
###===== PositiveIntegerField  => cruddals.PositiveInt
###===== SlugField             => cruddals.Slug
###===== URLField              => cruddals.URL
###===== BinaryField           => cruddals.URL

#? PositiveBigIntegerField
#?! CommaSeparateIntegerField (No esta en la doc)

#? FilePathField => graphene.String
#? PositiveSmallIntegerField => graphene.Int
#? SmallIntegerField => graphene.Int

#* Relationship fields
# ForeignKey
# ManyToManyField
# OneToOneField




#* Field types
# AutoField
# BigAutoField
# BigIntegerField
# BinaryField
# BooleanField
# CharField
# CommaSeparateIntegerField
# DateField
# DateTimeField
# DecimalField
# DurationField
# EmailField
# Field
# FileField
# FilePathField
# FloatField
# GenericIPAddressField
# IPAddressField
# ImageField
# IntegerField
# JSONField
# PositiveBigIntegerField
# PositiveIntegerField
# PositiveSmallIntegerField
# SlugField
# SmallAutoField
# SmallIntegerField
# TextField
# TimeField
# URLField
# UUIDField
#* Relationship fields
# ForeignKey
# ManyToManyField
# OneToOneField


# => graphene.Int
# => graphene.BigInt
# => graphene.Float
# => graphene.String
# => graphene.Boolean
# => graphene.ID
# => graphene.Base64
# => graphene.Date
# => graphene.DateTime
# => graphene.Time
# => graphene.Decimal
# => graphene.Enum
# => graphene.GenericScalar
# => graphene.JSONString
# => graphene.UUID



#form > AutoField #> AutoField
#form > BigAutoField #> BigAutoField
#form > BigIntegerField #> BigIntegerField
#form > BinaryField #> BinaryField
#form > BooleanField #> BooleanField
#form > CharField #> CharField
#form > DateField #> DateField
#form > DateTimeField #> DateTimeField
#form > DecimalField #> DecimalField
#form > DurationField #> DurationField
#form > EmailField #> EmailField
#form > FileField #> FileField
#form > FilePathField #> FilePathField
#form > FloatField #> FloatField
#form > GenericIPAddressField #> GenericIPAddressField
#form > IPAddressField #> IPAddressField
#form > ImageField  #> ImageField
#form > IntegerField #> IntegerField
#form > JSONField #> JSONField
#form > PositiveBigIntegerField #> PositiveBigIntegerField
#form > PositiveIntegerField #> PositiveIntegerField
#form > PositiveSmallIntegerField #> PositiveSmallIntegerField
#form > SlugField #> SlugField
#form > SmallAutoField #> SmallAutoField
#form > SmallIntegerField #> SmallIntegerField
#form > TextField #> TextField
#form > TimeField #> TimeField
#form > URLField #> URLField
#form > UUIDField #> UUIDField