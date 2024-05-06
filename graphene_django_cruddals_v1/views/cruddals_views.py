

import graphene

from cruddals_django.views.file_upload_graphql_view import FileUploadGraphQLView

from ..registry.registry_schema import get_global_registry_schema, set_global_registry_schema
from ..client.build_for_client import build_files_for_client_schema_cruddals
from ..main import CruddalsApp
from ..utils.utils import build_class, django_is_running_with_runserver, get_python_obj_from_string
from ..settings import cruddals_settings

from django.apps import apps as django_apps
from django.conf import settings
from django.core.management import call_command
from django.conf import settings
from django.test import override_settings

import os

import importlib
import shutil


class CRUDDALSView:

    @classmethod
    def _execute_test_cruddals(self):
        path_to_urls = settings.ROOT_URLCONF
        ls_path_to_urls = path_to_urls.split(".")
        name_file = ls_path_to_urls[-1]
        modulo = importlib.import_module(path_to_urls)
        ruta_archivo = modulo.__file__
        origen = ruta_archivo
        destino = ruta_archivo.replace(name_file, f"temp_{name_file}")
        shutil.copy(origen, destino)
        ls_path_to_urls[-1] = f"temp_{name_file}"
        new_path_to_urls = ".".join(ls_path_to_urls)

        @override_settings(ROOT_URLCONF=new_path_to_urls)
        def internal_execute_test_cruddals():
            """
                1. Como tengo las apps que cruddalizo, entonces puedo decir que creen archivos con el siguiente nombre cruddals_test.py
            """
            call_command('test', '--pattern=cruddals_test.py')

            print("----------------------------------")
            print("🎉🎉🎉=CRUDDALS IS WORKING=🎉🎉🎉")
            print("----------------------------------")
        
        internal_execute_test_cruddals()
        if os.path.exists(destino):
            os.remove(destino)

    @classmethod
    def validate_apps(self, apps_name):
        [django_apps.get_app_config(app_name) for app_name in apps_name]
    
    @classmethod
    def as_view(self, schema=None, default_schema=False, generate_cruddals_files_client=False, enable_test_cruddals=False, extra_queries=(), extra_mutations=() , **kwargs):
        if schema is None:
            schema = get_global_registry_schema()
            if schema is None:

                # CRUDDALS_DEFAULT_VIEW_USED = os.environ.get('CRUDDALS_DEFAULT_VIEW_USED')
                # if not CRUDDALS_DEFAULT_VIEW_USED:
                #     os.environ.setdefault('CRUDDALS_DEFAULT_VIEW_USED', 'True')
                try:
                    default_schema = True
                    
                    apps = cruddals_settings.APPS
                    
                    default_exclude_apps = ['graphene_django', 'messages', 'staticfiles', 'corsheaders', 'cruddals_django'] + cruddals_settings.EXCLUDE_APPS
                    
                    interfaces_for_project = cruddals_settings.INTERFACES
                    
                    final_interfaces_for_project = [get_python_obj_from_string(interface_for_project) for interface_for_project in interfaces_for_project]
                    
                    settings_for_apps = cruddals_settings.SETTINGS_FOR_APP
                    

                    self.validate_apps(settings_for_apps.keys())
                    self.apps_name = []
                    if apps == "__all__":
                        self.apps_name = django_apps.app_configs.keys()
                    elif isinstance(apps, (list, tuple,)):
                        self.apps_name = apps
                    elif isinstance(apps, dict):
                        self.apps_name = apps.keys()
                    self.validate_apps(self.apps_name)


                    queries = []
                    Q = None
                    mutations = []
                    M = None
                    self.apps_name = [item for item in self.apps_name if item not in default_exclude_apps]

                    for _name_app in self.apps_name:
                        
                        settings_of_app = settings_for_apps.get(_name_app, {})
                        final_exclude_models = settings_of_app.get("exclude_models", None)
                        final_models = None
                        if final_exclude_models is None:
                            _models = apps.get(_name_app, None) if isinstance(apps, dict) else None
                            final_models = settings_of_app.get("models", _models)

                        interfaces_of_app = settings_of_app.get("interfaces", [])
                        final_interfaces_of_app = [get_python_obj_from_string(interface_of_app) for interface_of_app in interfaces_of_app]
                        final_interfaces = final_interfaces_for_project + final_interfaces_of_app
                        
                        exclude_interfaces_of_app = settings_of_app.get("exclude_interfaces", [])
                        functions_of_app = settings_of_app.get("functions", [])
                        exclude_functions_of_app = settings_of_app.get("exclude_functions", [])
                        
                        final_settings_for_model = settings_of_app.get("settings_for_model", {})
                        for sett_model in final_settings_for_model.values():
                            if "interfaces" in sett_model:
                                sett_model["interfaces"] = [get_python_obj_from_string(interface_of_model) for interface_of_model in sett_model["interfaces"]]
                        
                        class AppSchema(CruddalsApp):
                            class Meta:
                                app_name = _name_app
                                
                                models = final_models
                                exclude_models = final_exclude_models
                                
                                interfaces = final_interfaces
                                exclude_interfaces = exclude_interfaces_of_app

                                functions = functions_of_app
                                exclude_functions = exclude_functions_of_app

                                settings_for_model = final_settings_for_model

                        queries.append(AppSchema.Query)
                        if AppSchema.Mutation:
                            mutations.append(AppSchema.Mutation)
                    
                    base = (graphene.ObjectType,)
                    queries = tuple(queries) + extra_queries + base
                    mutations = tuple(mutations) + extra_mutations
                    if mutations:
                        mutations = mutations + base
                        M = build_class( name='Mutation', bases=mutations)
                    Q = build_class( name='Query', bases=queries)
                    dict_for_schema = {"query": Q}
                    if M:
                        dict_for_schema.update({"mutation": M})
                    schema = graphene.Schema(**dict_for_schema)
                except Exception as e:
                    print("*******ERROR BUILDING CRUDDALS SCHEMA*******")
                    print(e)
                    print("*******ERROR BUILDING CRUDDALS SCHEMA*******\n\n")
                    
            else:
                if settings.DEBUG and enable_test_cruddals and django_is_running_with_runserver():
                    raise RuntimeError('Can use only one default schema CRUDDALS.')

        if default_schema is True and schema is not None:
            set_global_registry_schema(schema)
        if generate_cruddals_files_client:
            build_files_for_client_schema_cruddals(schema)
        if settings.DEBUG and enable_test_cruddals and django_is_running_with_runserver():
            self._execute_test_cruddals()
        return FileUploadGraphQLView.as_view(schema=schema, **kwargs)

