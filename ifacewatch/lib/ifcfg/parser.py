
import re
import socket

from .meta import MetaMixin
from .tools import exec_cmd, hex2dotted, minimal_logger

Log = minimal_logger(__name__)

class IfcfgParser(MetaMixin):
    class Meta:
        ifconfig_cmd_args = ['ifconfig', '-a']
        patterns = [
            '(?P<device>^[a-zA-Z0-9]+): flags=(?P<flags>.*) mtu (?P<mtu>.*)',
            '.*(inet )(?P<inet>[^\s]*).*',
            '.*(inet6 )(?P<inet6>[^\s]*).*',
            '.*(broadcast )(?P<broadcast>[^\s]*).*',
            '.*(netmask )(?P<netmask>[^\s]*).*',
            '.*(ether )(?P<ether>[^\s]*).*',
            '.*(prefixlen )(?P<prefixlen>[^\s]*).*',
            '.*(scopeid )(?P<scopeid>[^\s]*).*',
            '.*(ether )(?P<ether>[^\s]*).*',
            ]
        override_patterns = []

    def __init__(self, *args, **kw):
        super(IfcfgParser, self).__init__(*args, **kw)
        self._interfaces = {}
        self.ifconfig_data = kw.get('ifconfig', None)
        self.parse(self.ifconfig_data)

    def _get_patterns(self):
        return self._meta.patterns + self._meta.override_patterns

    def parse(self, ifconfig=None):
        """
        Parse ifconfig output into self._interfaces.

        Optional Arguments:

            ifconfig
                The data (stdout) from the ifconfig command.  Default is to
                call self._meta.ifconfig_cmd_args for the stdout.

        """
        _interfaces = []
        if not ifconfig:
            ifconfig, err, retcode = exec_cmd(self._meta.ifconfig_cmd_args)
        self.ifconfig_data = ifconfig
        cur = None
        all_keys = []

        for line in self.ifconfig_data.splitlines():
            for pattern in self._get_patterns():
                m = re.match(pattern, line)
                if m:
                    groupdict = m.groupdict()
                    # Special treatment to trigger which interface we're
                    # setting for if 'device' is in the line.  Presumably the
                    # device of the interface is within the first line of the
                    # device block.
                    if 'device' in groupdict:
                        cur = groupdict['device']
                        if not self._interfaces.has_key(cur):
                            self._interfaces[cur] = {}

                    for key in groupdict:
                        if key not in all_keys:
                            all_keys.append(key)
                        self._interfaces[cur][key] = groupdict[key]

        # fix it up
        self._interfaces = self.alter(self._interfaces)

        # standardize
        for key in all_keys:
            for device,device_dict in self._interfaces.items():
                if key not in device_dict:
                    self._interfaces[device][key] = None
                if type(device_dict[key]) == str:
                    self._interfaces[device][key] = device_dict[key].lower()


    def alter(self, interfaces):
        """
        Used to provide the ability to alter the interfaces dictionary before
        it is returned from self.parse().

        Required Arguments:

            interfaces
                The interfaces dictionary.

        Returns: interfaces dict

        """
        # fixup some things
        for device,device_dict in interfaces.items():
            if 'inet' in device_dict:
                try:
                    host = socket.gethostbyaddr(device_dict['inet'])[0]
                    interfaces[device]['hostname'] = host
                except socket.herror as e:
                    interfaces[device]['hostname'] = None

        return interfaces

    @property
    def interfaces(self):
        """
        Returns the full interfaces dictionary.

        """
        return self._interfaces

    @property
    def default_interface(self):
        """
        Returns the default interface device.

        """
        out, err, ret = exec_cmd(['/sbin/route', '-n'])
        lines = out.splitlines()
        for line in lines[2:]:
            if line.split()[0] == '0.0.0.0':
                iface = line.split()[-1]

        for interface in self.interfaces:
            if interface == iface:
                return self.interfaces[interface]
        return None # pragma: nocover

class UnixParser(IfcfgParser):
    def __init__(self, *args, **kw):
        super(UnixParser, self).__init__(*args, **kw)

class LinuxParser(UnixParser):
    def __init__(self, *args, **kw):
        super(LinuxParser, self).__init__(*args, **kw)

class Linux2Parser(LinuxParser):
    class Meta:
        override_patterns = [
            '(?P<device>^[a-zA-Z0-9]+)(.*)Link encap:(.*).*',
            '(.*)Link encap:(.*)(HWaddr )(?P<ether>[^\s]*).*',
            '.*(inet addr:)(?P<inet>[^\s]*).*',
            '.*(inet6 addr: )(?P<inet6>[^\s\/]*/(?P<prefixlen>[\d]*)).*',
            '.*(Bcast:)(?P<broadcast>[^\s]*).*',
            '.*(Mask:)(?P<netmask>[^\s]*).*',
            '.*(Scope:)(?P<scopeid>[^\s]*).*',
            ]

    def __init__(self, *args, **kw):
        super(Linux2Parser, self).__init__(*args, **kw)

class MacOSXParser(UnixParser):
    class Meta:
        override_patterns = [
            '.*(status: )(?P<status>[^\s]*).*',
            '.*(media: )(?P<media>.*)',
            ]

    def __init__(self, *args, **kw):
        super(MacOSXParser, self).__init__(*args, **kw)

    def parse(self, *args, **kw):
        super(MacOSXParser, self).parse(*args, **kw)

        # fix up netmask address for mac
        for device,device_dict in self.interfaces.items():
            if device_dict['netmask'] is not None:
                netmask = self.interfaces[device]['netmask']
                self.interfaces[device]['netmask'] = hex2dotted(netmask)

class FreeBSDParser(MacOSXParser):

    def __init__(self, *args, **kw):
        super(FreeBSDParser, self).__init__(*args, **kw)

    @property
    def default_interface(self):
        """
        Returns the default interface device.

        """
        out, err, ret = exec_cmd(['netstat', '-rn', '-f', 'inet'])
        lines = out.splitlines()
        iface = None
        for line in lines[2:]:
            if line.split()[0] == 'default':
                iface = line.split()[-1]

        for interface in self.interfaces:
            if interface == iface:
                return self.interfaces[interface]
        return None # pragma: nocover
