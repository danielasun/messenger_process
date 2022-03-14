# Daniel Sun 14 Oct 2019
# Contains enums to use as inter-process communication between ProcessManagers.
# Use these to indicate status as well as success/failure.
# rml_ws

import enum

DXL_SIGNAL = enum.Enum('DXL_SIGNAL', 'INITIALIZATION_COMPLETE')

VREP_SIGNAL = enum.Enum('VREP_SIGNAL', 'INITIALIZATION_COMPLETE')

BULLET_SIGNAL = enum.Enum('BULLET_SIGNAL', 'INITIALIZATION_COMPLETE')

DMPC_SIGNAL = enum.Enum('DMPC_SIGNAL', 'REQUESTING_PLAN PLANNING_COMPLETE PLANNING_FAILURE')

MESSENGER_SIGNAL = enum.Enum('MESSENGER_SIGNAL', 'A B C')

MP_TRANSPORT = enum.Enum('MP_TRANSPORT', 'STOP HEARTBEAT')

JLC_SIGNAL = enum.Enum('JLC_SIGNAL', 'STARTING_CONTROL_LOOP')

