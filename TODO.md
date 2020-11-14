# Need to send: Current, voltage, fan1, fan2, temp1, tempsetpoint

# Need to set: temp, fan1, fan2, string for heater serial port

# Need to log: temp1, temp2, current, voltage, timestamp, fan1, fan2

# TODO:

# Add class to handle serial connection. Getter and setter, and init.

# Add logging code to server/PiccoloCoolBoxControl - logging code on 129.

# Add fans (2 of them) in the server/PiccoloConfig.py, as well as voltage sensor, serial location, coolbox log location path, and current sensor.

# Make new fan class. Then on line 114 - 116 of coolboxControl class, register the fan classes

# Make new voltage class. Then on line 114 - 116 of coolboxControl class, register the voltage classes

# Make new current class. Then on line 114 - 116 of coolboxControl class, register the current classes

# Proxy classes

# Add proxy classes for fan / voltage / current classes

# Ammend temp and control proxy classes

# Done:

# Temperature class is basically done.

# Registering the temperature class is done
