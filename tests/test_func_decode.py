import pytest
from mochad_dispatch.main import MochadClient

MOCHAD_FUNCS = {
      'Motion_alert_MS10A': {
          'device_type': 'MS10A',
          'event_type': 'motion',
          'event_state': 'alert',
      },
      'Motion_normal_MS10A': {
          'device_type': 'MS10A',
          'event_type': 'motion',
          'event_state': 'normal',
      },
      'Motion_alert_low_MS10A': {
          'device_type': 'MS10A',
          'event_type': 'motion',
          'event_state': 'alert',
          'low_battery': True,
      },
      'Motion_normal_low_MS10A': {
          'device_type': 'MS10A',
          'event_type': 'motion',
          'event_state': 'normal',
          'low_battery': True,
      },

      'Motion_alert_SP554A': {
          'device_type': 'SP554A',
          'event_type': 'motion',
          'event_state': 'alert',
      },
      'Motion_normal_SP554A': {
          'device_type': 'SP554A',
          'event_type': 'motion',
          'event_state': 'normal',
      },
      'Motion_alert_Home_Away_SP554A': {
          'device_type': 'SP554A',
          'event_type': 'motion',
          'event_state': 'alert',
          'home_away': True,
      },
      'Motion_normal_Home_Away_SP554A': {
          'device_type': 'SP554A',
          'event_type': 'motion',
          'event_state': 'normal',
          'home_away': True,
      },

      'Contact_alert_min_DS10A': {
          'device_type': 'DS10A',
          'event_type': 'contact',
          'event_state': 'alert',
          'delay': 'min',
      },
      'Contact_normal_min_DS10A': {
          'device_type': 'DS10A',
          'event_type': 'contact',
          'event_state': 'normal',
          'delay': 'min',
      },
      'Contact_alert_max_DS10A': {
          'device_type': 'DS10A',
          'event_type': 'contact',
          'event_state': 'alert',
          'delay': 'max',
      },
      'Contact_normal_max_DS10A': {
          'device_type': 'DS10A',
          'event_type': 'contact',
          'event_state': 'normal',
          'delay': 'max',
      },
      'Contact_alert_min_low_DS10A': {
          'device_type': 'DS10A',
          'event_type': 'contact',
          'event_state': 'alert',
          'delay': 'min',
          'low_battery': True,
      },
      'Contact_normal_min_low_DS10A': {
          'device_type': 'DS10A',
          'event_type': 'contact',
          'event_state': 'normal',
          'delay': 'min',
          'low_battery': True,
      },
      'Contact_alert_max_low_DS10A': {
          'device_type': 'DS10A',
          'event_type': 'contact',
          'event_state': 'alert',
          'delay': 'max',
          'low_battery': True,
      },
      'Contact_normal_max_low_DS10A': {
          'device_type': 'DS10A',
          'event_type': 'contact',
          'event_state': 'normal',
          'delay': 'max',
          'low_battery': True,
      },

      'Contact_alert_min_tamper_DS12A': {
          'device_type': 'DS12A',
          'event_type': 'contact',
          'event_state': 'alert',
          'delay': 'min',
          'tamper': True,
      },
      'Contact_normal_min_tamper_DS12A': {
          'device_type': 'DS12A',
          'event_type': 'contact',
          'event_state': 'normal',
          'delay': 'min',
          'tamper': True,
      },
      'Contact_alert_max_tamper_DS12A': {
          'device_type': 'DS12A',
          'event_type': 'contact',
          'event_state': 'alert',
          'delay': 'max',
          'tamper': True,
      },
      'Contact_normal_max_tamper_DS12A': {
          'device_type': 'DS12A',
          'event_type': 'contact',
          'event_state': 'normal',
          'delay': 'max',
          'tamper': True,
      },
      'Arm_KR10A': {
          'device_type': 'KR10A',
          'command': 'arm',
      },
      'Disarm_KR10A': {
          'device_type': 'KR10A',
          'command': 'disarm',
      },
      'Lights_On_KR10A': {
          'device_type': 'KR10A',
          'command': 'lights_on',
      },
      'Lights_Off_KR10A': {
          'device_type': 'KR10A',
          'command': 'lights_off',
      },
      'Panic_KR10A': {
          'device_type': 'KR10A',
          'command': 'panic',
      },

      'Panic_KR15A': {
          'device_type': 'KR15A',
          'command': 'panic',
      },

      'Arm_Home_min_SH624': {
          'device_type': 'SH624',
          'command': 'arm_home',
          'delay': 'min',
      },
      'Arm_Away_min_SH624': {
          'device_type': 'SH624',
          'command': 'arm_away',
          'delay': 'min',
      },
      'Arm_Home_max_SH624': {
          'device_type': 'SH624',
          'command': 'arm_home',
          'delay': 'max',
      },
      'Arm_Away_max_SH624': {
          'device_type': 'SH624',
          'command': 'arm_away',
          'delay': 'max',
      },
      'Disarm_SH624': {
          'device_type': 'SH624',
          'command': 'disarm',
      },
      'Panic_SH624': {
          'device_type': 'SH624',
          'command': 'panic',
      },
      'Lights_On_SH624': {
          'device_type': 'SH624',
          'command': 'lights_on',
      },
      'Lights_Off_SH624': {
          'device_type': 'SH624',
          'command': 'lights_off',
      },
      }

def test_known_funcs():
    for func_raw, func_dict in MOCHAD_FUNCS.items():
        result = MochadClient.decode_func(None, func_raw)
        print(func_dict, result)
        assert result == func_dict
