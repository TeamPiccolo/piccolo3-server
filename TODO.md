# TODO list

Need to send: Current, voltage, fan1, fan2, temp1, tempsetpoint

Need to set: temp, fan1, fan2, string for heater serial port

Need to log: temp1, temp2, current, voltage, timestamp, fan1, fan2

## Pending work

- server/PiccoloConfig.py
  - ~~Add fans x2~~
  - ~~voltage sensor~~
  - ~~current sensor~~
  - ~~serial location~~
  - ~~coolbox log location path~~
- server/PiccoloCoolboxControl.py
  - ~~Add parent class to handle serial connection. Getter and setter, and init.~~
  - ~~Make new fan class.~~
  - ~~Then on line 114 - 116 of coolboxControl class, register the fan classes~~
  - ~~Make new voltage class.~~
  - ~~Then on line 114 - 116 of coolboxControl class, register the voltage classes~~
  - ~~Make new current class.~~
  - ~~Then on line 114 - 116 of coolboxControl class, register the current classes~~
  - Add logging code to server/PiccoloCoolBoxControl - logging code on 129.
- Proxy classes
  - Add proxy classes for fan / voltage / current classes
  - Ammend temp and control proxy classes

## Done:

- Temperature class is basically done by Magi.
- Registering the temperature class is done by Magi.
