# Copyright 2017-2019 TensorHub, Inc.
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

from __future__ import absolute_import
from __future__ import division

import re
import yaml

import six

FUNCTION_P = re.compile(r"([a-zA-Z0-9_\-\.]*)\[(.*)\]\s*$")
FUNCTION_ARG_DELIM = ":"

DEFAULT_FLOAT_TRUNC_LEN = 5

def encode_flag_val(val):
    if val is True:
        return "yes"
    elif val is False:
        return "no"
    elif val is None:
        return "null"
    elif isinstance(val, list):
        return _encode_list(val)
    elif isinstance(val, float):
        return _yaml_encode(val)
    elif isinstance(val, six.string_types):
        return _encode_str(val)
    elif isinstance(val, dict):
        return _encode_dict(val)
    else:
        return str(val)

def _encode_list(val_list):
    joined = ", ".join([encode_flag_val(val) for val in val_list])
    return "[%s]" % joined

def _yaml_encode(val):
    return _strip_yaml(yaml.safe_dump(val).strip())

def _strip_yaml(s):
    if s.endswith("\n..."):
        return s[:-4]
    return s

def _encode_str(s):
    return _quote_float(_yaml_encode(s))

def _encode_dict(d):
    encoded_kv = [
        (encode_flag_val(k), encode_flag_val(v))
        for k, v in sorted(d.items())]
    return "{%s}" % ", ".join(["%s: %s" % kv for kv in encoded_kv])

def _quote_float(s):
    """Returns s quoted if s can be coverted to a float."""
    try:
        float(s)
    except ValueError:
        return s
    else:
        return "'%s'" % s

def decode_flag_val(s):
    if s == "":
        return s
    decoders = [
        (int, ValueError),
        (_yaml_parse, (ValueError, yaml.YAMLError)),
    ]
    for f, e_type in decoders:
        try:
            return f(s)
        except e_type:
            pass
    return s

def _yaml_parse(s):
    """Uses yaml module to parse s to a Python value.

    First tries to parse as an unnamed flag function with at least two
    args and, if successful, returns s unmodified. This prevents yaml
    from attempting to parse strings like '1:1' which it considers to
    be timestamps.
    """
    try:
        name, args = decode_flag_function(s)
    except ValueError:
        pass
    else:
        if name is None and len(args) >= 2:
            return s
    return yaml.safe_load(s)

def decode_flag_function(s):
    if not isinstance(s, six.string_types):
        raise ValueError("requires string")
    m = FUNCTION_P.match(s)
    if not m:
        raise ValueError("not a function")
    name = m.group(1) or None
    args_raw = m.group(2).strip()
    if args_raw:
        args_s = args_raw.split(FUNCTION_ARG_DELIM)
    else:
        args_s = []
    args = [decode_flag_val(arg.strip()) for arg in args_s]
    return name, tuple(args)

def format_flags(flags, truncate_floats=False):
    return [
        _flag_assign(name, val, truncate_floats)
        for name, val in sorted(flags.items())]

def _flag_assign(name, val, truncate_floats):
    return "%s=%s" % (name, format_flag(val, truncate_floats))

def format_flag(val, truncate_floats=False):
    fmt_val = encode_flag_val(val)
    if truncate_floats and isinstance(val, float):
        trunc_len = _trunc_len(truncate_floats)
        fmt_val = _truncate_formatted_float(fmt_val, trunc_len)
    return _quote_encoded(fmt_val, val)

def _trunc_len(truncate_floats):
    if truncate_floats is True:
        return DEFAULT_FLOAT_TRUNC_LEN
    if not isinstance(truncate_floats, int):
        raise ValueError(
            "invalid value for truncate_floats: %r (expected int)"
            % truncate_floats)
    return truncate_floats

def _quote_encoded(encoded, val):
    if _needs_quote(encoded, val):
        return _quote(encoded)
    return encoded

def _needs_quote(encoded, val):
    return (
        isinstance(val, six.string_types) and
        " " in encoded and
        encoded[0] not in ("'", "\""))

def _quote(s):
    return repr(s)

def _truncate_formatted_float(s, trunc_len):
    parts = re.split(r"(\.[0-9]+)", s)
    return "".join([
        _maybe_truncate_dec_part(part, trunc_len)
        for part in parts])

def _maybe_truncate_dec_part(part, trunc_len):
    if part[:1] != ".":
        return part
    if len(part) <= trunc_len: # lte to include leading '.'
        return part
    return part[:trunc_len + 1]
