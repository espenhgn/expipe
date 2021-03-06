import datetime
import exdir
import os
import uuid
import pyrebase
import configparser
from expipe import settings

# TODO add attribute managers to allow changing values of modules and actions

datetime_format = '%Y-%m-%dT%H:%M:%S'

class ActionManager:
    def __init__(self, project):
        self.project = project

    def __getitem__(self, name):
        result = db.child("actions").child(self.project.id).child(name).get(user["idToken"]).val()
        if not result:
            raise KeyError("Action '" + name + "' does not exist.")
        return Action(project=self.project, action_id=name)


class Project:
    def __init__(self, project_id):
        self.id = project_id
        self.datetime_format = '%Y-%m-%dT%H:%M:%S'

    @property
    def actions(self):
        return ActionManager(self)

    def require_action(self, name):
        result = db.child("actions").child(self.id).child(name).get(user["idToken"]).val()
        if not result:
            dtime = datetime.datetime.today().strftime(self.datetime_format)
            result = db.child("actions").child(self.id).child(name).update({"registered": dtime}, user["idToken"])
        return Action(self, name)

class Datafile:
    def __init__(self, action):
        self.action = action
        action_datafile_directory = os.path.join(settings["data_path"], action.project)
        os.makedirs(action_datafile_directory, exist_ok=True)
        self.exdir_path = os.path.join(action_datafile_directory, action.id + ".exdir")
        self.exdir_file = exdir.File(self.exdir_path)
        data = {
            "type": "exdir",
            "exdir_path": self.exdir_path
        }
        db.child("datafiles").child(self.action.project.id).child(self.action.id).child("main").set(data, user["idToken"])


class FirebaseBackend:
    def __init__(self, path):
        self.path = path

    def exists(self):
        value = self.get()
        if value:
            return True
        else:
            return False

    def get(self, name=None):
        if name is None:
            value = db.child(self.path).get(user["idToken"]).val()
        else:
            value = db.child(self.path).child(name).get(user["idToken"]).val()
        value = exdir.core.convert_back_quantities(value)
        return value

    def set(self, name, value=None):
        if value is None:
            value = name
            value = exdir.core.convert_quantities(value)
            db.child(self.path).set(value, user["idToken"])
        else:
            value = exdir.core.convert_quantities(value)
            db.child(self.path).child(name).set(value, user["idToken"])

    def update(self, name, value=None):
        if value is None:
            value = name
            value = exdir.core.convert_quantities(value)
            db.child(self.path).update(value, user["idToken"])
        else:
            value = exdir.core.convert_quantities(value)
            db.child(self.path).child(name).update(value, user["idToken"])


class Module:
    def __init__(self, action, module_id):
        self.action = action
        self.id = module_id
        path = "/".join(["modules", self.action.project.id, self.action.id, self.id])
        self._firebase = FirebaseBackend(path)

    def to_dict(self):
        return self._firebase.get()


class ModuleManager:
    def __init__(self, action):
        self.action = action

    def __getitem__(self, name):
        return Module(self.action, name)

    def __iter__(self):
        for name in self.keys():
            yield name

    def __contains__(self, name):
        return name in self.keys()

    def keys(self):
        result = db.child("modules").child(self.action.project.id).child(self.action.id).get(user["idToken"]).val()
        return result or list()


class Filerecord:
    def __init__(self, action, filerecord_id=None):
        self.id = filerecord_id or "main"  # oneliner hack by Mikkel
        self.action = action

        # TODO make into properties/functions in case settings change
        self.exdir_path = action.project.id + "/" + action.id + "/" + self.id + ".exdir"
        self.local_path = os.path.join(settings["data_path"], self.exdir_path)
        path_split = self.local_path.split("/")
        directory = "/".join(path_split[:-1])
        if not os.path.exists(directory):
            print("MAKING DIRECTORY", self.local_path)
            os.makedirs(directory)

        # TODO if not exists and not required, return error
        ref_path = "/".join(["files", action.project.id, action.id, self.id])

        if not db.child(ref_path).get(user["idToken"]).val():
            db.child(ref_path).update({"path": self.exdir_path}, user["idToken"])


class Action:
    def __init__(self, project, action_id):
        self.project = project
        self.id = action_id
        path = "/".join(["actions", self.project.id, self.id])
        self._firebase = FirebaseBackend(path)

    @property
    def location(self):
        return db.child(self._firebase.path).child('location').get(user['idToken']).val()

    @location.setter
    def location(self, value):
        if not isinstance(value, str):
            raise ValueError('Location requires string')
        db.child(self._firebase.path).child('location').set(value, user['idToken'])

    @property
    def type(self):
        return db.child(self._firebase.path).child('type').get(user['idToken']).val()

    @type.setter
    def type(self, value):
        if not isinstance(value, str):
            raise ValueError('Type requires string')
        db.child(self._firebase.path).child('type').set(value, user['idToken'])

    @property
    def subjects(self):
        return db.child(self._firebase.path).child('subjects').get(user['idToken']).val()

    @subjects.setter
    def subjects(self, value):
        if not isinstance(value, dict):
            raise ValueError('Users requires dict e.g. "{"1685": "true"}"')
        db.child(self._firebase.path).child('subjects').set(value, user['idToken'])

    @property
    def datetime(self):
        return db.child(self._firebase.path).child('datetime').get(user['idToken']).val()

    @datetime.setter
    def datetime(self, value):
        if not isinstance(value, datetime.datetime):
            raise ValueError('Datetime requires a datetime object with format')
        dtime = value.strftime(self.project.datetime_format)
        db.child(self._firebase.path).child('datetime').set(dtime, user['idToken'])

    @property
    def users(self):
        return db.child(self._firebase.path).child('users').get(user['idToken']).val()

    @users.setter
    def users(self, value):
        if not isinstance(value, dict):
            raise ValueError('Users requires dict e.g. "{"Kristian": "true"}"')
        db.child(self._firebase.path).child('users').set(value, user['idToken'])

    @property
    def modules(self):
        # TODO consider adding support for non-shallow fetching
        return ModuleManager(self)

    def require_module(self, name=None, template=None, contents=None,
                       overwrite=False):
        if name is None and template is not None:
            template_object = db.child("/".join(["templates", template])).get(user["idToken"]).val()
            name = template_object["identifier"]
        if template is None and name is None:
            raise ValueError('name and template cannot both be None')
        module = Module(action=self, module_id=name)
        if not module._firebase.exists() and template is not None:
            template_contents = db.child("/".join(["templates_contents", template])).get(user["idToken"]).val()
            if contents is not None:
                raise NotImplementedError('we do not support require_module with contents')
            contents = template_contents
            module._firebase.set(contents)
        if not module._firebase.exists() and template is None:
            if contents is not None:
                if not isinstance(contents, dict):
                    raise ValueError('contents must be of type: dict')
                module._firebase.set(contents)
        if module._firebase.exists() and template is None:
            if contents is not None and overwrite:
                if not isinstance(contents, dict):
                    raise ValueError('contents must be of type: dict')
                module._firebase.set(contents)
            if contents is not None and not overwrite:
                raise ValueError('Set overwrite to true if you want to ' +
                                 'overwrite the contents on the database')
        return module

    def require_filerecord(self, class_type=None, name=None):
        class_type = class_type or Filerecord
        return class_type(self, name)


def get_project(project_id):
    existing = db.child("/".join(["projects", project_id])).get(user["idToken"]).val()
    if not existing:
        raise NameError("Project " + project_id + " does not exist.")
    return Project(project_id)


def require_project(project_id):
    """Creates a new project with the provided id."""
    existing = db.child("/".join(["projects", project_id])).get(user["idToken"]).val()
    registered = datetime.datetime.today().strftime(datetime_format)
    if not existing:
        db.child("/".join(["projects", project_id])).set({"registered": registered}, user["idToken"])
    return Project(project_id)


def create_datafile(action):
    """
    Creates a new dataset on disk and registers it on the action.
    """
    datafile = Datafile(action)
    datafile.exdir_file.create_group("test")
    return datafile.exdir_file

def find_action(project, user=None, subject=None):
    print("Looking for action by user")
    return None


def _init_module():
    """
    Helper function, which can abort if loading fails.
    """
    global auth, user, db
    config = settings['firebase']['config']

    firebase = pyrebase.initialize_app(config)

    try:
        email = settings['firebase']['email']
        password = settings['firebase']['password']
        auth = firebase.auth()
        user = None
        if email and password:
            user = auth.sign_in_with_email_and_password(email, password)
        db = firebase.database()
    except KeyError:
        print("Could not find email and password in configuration.\n"
              "Try running expipe.configure() again.\n"
              "For more info see:\n\n"
              "\texpipe.configure?\n\n")
        # raise ImportError("Configuration not complete. See details in output.")

    return True

_init_module()

# def create_experiment(session_id, session_start_time, experimenter, session_description="", notes=""):
#     # TODO do we need to require session_id?
#     print(settings)
#
#     unique_id = str(uuid.uuid4())
#     unique_id_short = unique_id.split("-")[0]
#     registration_datetime = datetime.datetime.now()
#     year_folder_name = '{:%Y}'.format(registration_datetime)
#     month_folder_name = '{:%Y-%m}'.format(registration_datetime)
#     exdir_folder_name = '{:%Y-%m-%d-%H%M%S}_{}.exdir'.format(registration_datetime, unique_id_short)
#     parent_path = os.path.join(settings["data_path"],
#                                year_folder_name,
#                                month_folder_name)
#     if not os.path.exists(parent_path):
#         os.makedirs(parent_path)
#     exdir_folder_path = os.path.join(parent_path,
#                                      exdir_folder_name)
#     f = exdir.File(exdir_folder_path)
#     f.attrs["identifier"] = str(unique_id)
#     f.attrs["nwb_version"] = "NWB-1.0.3"
#     f.attrs["file_create_date"] = datetime.datetime.now().isoformat()
#     f.attrs["session_start_time"] = session_start_time
#     f.attrs["session_description"] = session_description
#
#     general = f.create_group("general")
#     general.attrs["session_id"] = session_id
#     general.attrs["experimenter"] = experimenter
#     general.attrs["notes"] = notes
#     # TODO add all /general info from NWB
#
#     f.create_group("acquisition")
#     f.create_group("stimulus")
#     f.create_group("epochs")
#     f.create_group("processing")
#     f.create_group("analysis")
#
#     # TODO add record to database
#
#     # TODO return both ID and file?
#
#     return f
