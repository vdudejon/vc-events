from pyVmomi import vim, vmodl


class PcFilter(object):
    """
    Class to simplify the property collector usage.
    Call wait once to generate the initial properties.
    Subsequent calls will wait for updates.
    """

    def __init__(self, obj, props):
        self.obj = obj
        self.pc = self._get_pc().CreatePropertyCollector()
        self.props = props
        self.pcFilter = None
        self.version = ""

    def __enter__(self):
        PC = vmodl.query.PropertyCollector
        filterSpec = PC.FilterSpec()
        objSpec = PC.ObjectSpec(obj=self.obj)
        filterSpec.objectSet.append(objSpec)
        propSet = PC.PropertySpec(all=False)
        propSet.type = type(self.obj)
        propSet.pathSet = self.props
        filterSpec.propSet = [propSet]
        self.pcFilter = self.pc.CreateFilter(filterSpec, False)
        return self

    def __exit__(self, *args):
        if self.pcFilter is not None:
            self.pcFilter.Destroy()
        if self.pc is not None:
            self.pc.Destroy()

    def wait(self, timeout=None):
        options = vmodl.query.PropertyCollector.WaitOptions()
        options.maxWaitSeconds = timeout
        update = self.pc.WaitForUpdatesEx(self.version, options)
        if update is not None:
            self.version = update.version
        return update

    def _get_si(self):
        return vim.ServiceInstance("ServiceInstance", stub=self.obj._stub)

    def _get_pc(self):
        return self._get_si().content.propertyCollector
