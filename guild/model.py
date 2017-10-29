# Copyright 2017 TensorHub, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import hashlib
import logging
import os
import sys

import pkg_resources

from guild import entry_point_util
from guild import modelfile
from guild import namespace

_models = entry_point_util.EntryPointResources("guild.models", "model")

class Model(object):

    def __init__(self, ep):
        self.name = ep.name
        self.dist = ep.dist
        self.modeldef = _modeldef_for_dist(ep.name, ep.dist)
        self._fullname = None # lazy

    def __repr__(self):
        return "<guild.model.Model '%s'>" % self.name

    @property
    def fullname(self):
        if self._fullname is None:
            pkg_name = namespace.apply_namespace(self.dist.project_name)
            self._fullname = "%s/%s" % (pkg_name, self.name)
        return self._fullname

    @property
    def reference(self):
        try:
            modelfile = self.dist.modelfile
        except AttributeError:
            return "dist:%s %s" % (self.dist, self.name)
        else:
            return "file:%s %s" % (_modelfile_dist_ref(modelfile), self.name)

def _modeldef_for_dist(name, dist):
    if isinstance(dist, ModelfileDistribution):
        return dist.get_model(name)
    else:
        for modeldef in _ensure_dist_modeldefs(dist):
            if modeldef.name == name:
                return modeldef
        raise ValueError("undefined model '%s'" % name)

def _ensure_dist_modeldefs(dist):
    if not hasattr(dist, "_modelefs"):
        dist._modeldefs = _load_dist_modeldefs(dist)
    return dist._modeldefs

def _load_dist_modeldefs(dist):
    modeldefs = []
    try:
        record = dist.get_metadata_lines("RECORD")
    except IOError:
        logging.warning(
            "distribution %s missing RECORD metadata - unable to find models",
            dist)
    else:
        for line in record:
            path = line.split(",", 1)[0]
            if os.path.basename(path) in modelfile.NAMES:
                fullpath = os.path.join(dist.location, path)
                _try_acc_modeldefs(fullpath, modeldefs)
    return modeldefs

def _try_acc_modeldefs(path, acc):
    try:
        models = modelfile.from_file(path)
    except Exception as e:
        logging.warning("unable to load models from %s: %s", path, e)
    else:
        for modeldef in models:
            acc.append(modeldef)

def _modelfile_dist_ref(modelfile):
    path = os.path.abspath(modelfile.src)
    return "%s %s" % (path, _modelfile_hash(path))

def _modelfile_hash(path):
    try:
        path_bytes = open(path, "rb").read()
    except IOError:
        logging.warning("unable to read %s to calculate modelfile hash", path)
        return "-"
    else:
        return hashlib.md5(path_bytes).hexdigest()

class ModelfileDistribution(pkg_resources.Distribution):

    def __init__(self, modelfile):
        super(ModelfileDistribution, self).__init__(
            modelfile.src, project_name=_modelfile_project_name(modelfile))
        self.modelfile = modelfile
        self._entry_map = _modelfile_entry_map(modelfile, self)

    def __repr__(self):
        return "<guild.model.ModelfileDistribution '%s'>" % self.modelfile.src

    def get_entry_map(self, group=None):
        if group is None:
            return self._entry_map
        else:
            return self._entry_map.get(group, {})

    def get_model(self, name):
        for model in self.modelfile:
            if model.name == name:
                return model
        raise ValueError(name)

def _modelfile_project_name(modelfile):
    """Returns a project name for a modelfile distribution.

    Modelfile distribution project names are of the format:

        '.modelfile.' + ESCAPED_MODELFILE_PATH

    ESCAPED_MODELFILE_PATH is a 'safe' project name (i.e. will not be
    modified in a call to `pkg_resources.safe_name`) that, when
    unescaped using `_unescape_project_name`, is the relative path of
    the directory containing the modelfile. The modefile name itself
    (e.g. 'MODEL' or 'MODELS') is not contained in the path.

    Modelfile paths are relative to the current working directory
    (i.e. the value of os.getcwd() at the time they are generated) and
    always start with '.'.
    """
    pkg_path = os.path.relpath(os.path.dirname(modelfile.src))
    if pkg_path[0] != ".":
        pkg_path = os.path.join(".", pkg_path)
    safe_path = _escape_project_name(pkg_path)
    return ".modelfile.%s" % safe_path

def _escape_project_name(name):
    """Escapes name for use as a valie pkg_resources project name."""
    return str(base64.b16encode(name.encode("utf-8")).decode("utf-8"))

def _unescape_project_name(escaped_name):
    """Unescapes names escaped with `_escape_project_name`."""
    return str(base64.b16decode(escaped_name).decode("utf-8"))

def _modelfile_entry_map(modelfile, dist):
    return {
        "guild.models": {
            model.name: _model_entry_point(model, dist)
            for model in modelfile
        },
        "guild.resources": {
            res.name: _resource_entry_point(res.name, dist)
            for res in _iter_resources(modelfile)
        }
    }

def _model_entry_point(model, dist):
    return pkg_resources.EntryPoint(
        name=model.name,
        module_name='guild.model',
        attrs=('Model',),
        dist=dist)

def _iter_resources(modelfile):
    for model in modelfile:
        for res in model.resources:
            yield res

def _resource_entry_point(name, dist):
    return pkg_resources.EntryPoint(
        name=name,
        module_name='guild.resource',
        attrs=('Resource',),
        dist=dist)

class ModelImportError(ImportError):
    pass

class ModelImporter(object):

    def __init__(self, path):
        if not os.path.isdir(path):
            raise ModelImportError(path)
        path_names = os.listdir(path)
        for modelfile_name in modelfile.NAMES:
            if modelfile_name in path_names:
                break
        else:
            raise ModelImportError(path)

    @staticmethod
    def find_module(_fullname, _path=None):
        return None

def _model_finder(_importer, path, _only=False):
    try:
        models = modelfile.from_dir(path)
    except (IOError,
            modelfile.ModelfileFormatError,
            modelfile.ModelfileReferenceError) as e:
        logging.warning(
            "unable to load model from '%s': %s",
            path, e)
    else:
        yield ModelfileDistribution(models)

class ModelfileNamespace(namespace.Namespace):

    @staticmethod
    def pip_install_info(_name):
        raise TypeError("modelfiles cannot be installed using pip")

    @staticmethod
    def is_project_name_member(name):
        if name.startswith(".modelfile."):
            parts = name[11:].split("/", 1)
            project_name = _unescape_project_name(parts[0])
            rest = "/" + parts[1] if len(parts) == 2 else ""
            return namespace.Membership.yes, project_name + rest
        else:
            return namespace.Membership.no, None

def get_path():
    return _models.path()

def set_path(path):
    _models.set_path(path)

def add_model_path(model_path):
    path = _models.path()
    try:
        path.remove(model_path)
    except ValueError:
        pass
    path.insert(0, model_path)
    _models.set_path(path)

def iter_models():
    for _name, model in _models:
        if not model.modeldef.private:
            yield model

def for_name(name):
    return _models.for_name(name)

def iter_():
    for _name, model in _models:
        if not model.modeldef.private:
            yield model

def _register_model_finder():
    sys.path_hooks.insert(0, ModelImporter)
    pkg_resources.register_finder(ModelImporter, _model_finder)

_register_model_finder()
