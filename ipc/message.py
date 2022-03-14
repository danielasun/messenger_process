def create_message(type, **kwargs):
    """
    helper function to create messages
    :param type:
    :param kwargs:
    :return:
    """
    msg = Message(type)
    for k, v in kwargs.items():
        msg[k] = v
    return msg


class Message(dict):
    """
    Somewhat standardized dictionary that always makes sure that you have a
    signal type.
    """

    def __init__(self, type):
        """

        :param type: a signal from pebl.ipc.signals
        """
        super().__init__()
        self['type'] = type

    @property
    def type(self):
        return self['type']