
import time
import digitalio
from micropython import const

usleep = lambda x: time.sleep(x/1000000.0)

# pylint: disable-msg=bad-whitespace
# Commands
_LCD_CLEARDISPLAY        = const(0x01)
_LCD_RETURNHOME          = const(0x02)
_LCD_ENTRYMODESET        = const(0x04)
_LCD_DISPLAYCONTROL      = const(0x08)
_LCD_CURSORSHIFT         = const(0x10)
_LCD_FUNCTIONSET         = const(0x20)
_LCD_SETCGRAMADDR        = const(0x40)
_LCD_SETDDRAMADDR        = const(0x80)

# Entry flags
_LCD_ENTRYLEFT           = const(0x02)
_LCD_ENTRYSHIFTDECREMENT = const(0x00)

# Control flags
_LCD_DISPLAYON           = const(0x04)
_LCD_CURSORON            = const(0x02)
_LCD_CURSOROFF           = const(0x00)
_LCD_BLINKON             = const(0x01)
_LCD_BLINKOFF            = const(0x00)

# Move flags
_LCD_DISPLAYMOVE         = const(0x08)
_LCD_MOVERIGHT           = const(0x04)
_LCD_MOVELEFT            = const(0x00)

# Function set flags
_LCD_4BITMODE            = const(0x00)
_LCD_2LINE               = const(0x08)
_LCD_1LINE               = const(0x00)
_LCD_5X8DOTS             = const(0x00)

# Offset for up to 4 rows.
_LCD_ROW_OFFSETS         = (0x00, 0x40, 0x14, 0x54)

# Flags for RS pin modes
_RS_INSTRUCTION          = const(0x00)
_RS_DATA                 = const(0x01)


# pylint: enable-msg=bad-whitespace

# pylint: disable-msg=too-many-instance-attributes
class Character_LCD:
    """Base class for character LCD.
    :param ~digitalio.DigitalInOut rs: The reset data line
    :param ~digitalio.DigitalInOut en: The enable data line
    :param ~digitalio.DigitalInOut d4: The data line 4
    :param ~digitalio.DigitalInOut d5: The data line 5
    :param ~digitalio.DigitalInOut d6: The data line 6
    :param ~digitalio.DigitalInOut d7: The data line 7
    :param columns: The columns on the charLCD
    :param lines: The lines on the charLCD
    """
    LEFT_TO_RIGHT = const(0)
    RIGHT_TO_LEFT = const(1)

    # pylint: disable-msg=too-many-arguments
    def __init__(self, interface, rs, en, d4, d5, d6, d7, columns, lines
                ):

        self.columns = columns
        self.lines = lines
        #  save pin numbers
        self.reset = rs
        self.enable = en
        self.dl4 = d4
        self.dl5 = d5
        self.dl6 = d6
        self.dl7 = d7

        self.interface = interface

        # Initialise the display
        self._write8(0x33)
        self._write8(0x32)
        # Initialise display control
        self.displaycontrol = _LCD_DISPLAYON | _LCD_CURSOROFF | _LCD_BLINKOFF
        # Initialise display function
        self.displayfunction = _LCD_4BITMODE | _LCD_1LINE | _LCD_2LINE | _LCD_5X8DOTS
        # Initialise display mode
        self.displaymode = _LCD_ENTRYLEFT | _LCD_ENTRYSHIFTDECREMENT
        # Write to displaycontrol
        self._write8(_LCD_DISPLAYCONTROL | self.displaycontrol)
        # Write to displayfunction
        self._write8(_LCD_FUNCTIONSET | self.displayfunction)
        # Set entry mode
        self._write8(_LCD_ENTRYMODESET | self.displaymode)
        self.clear()

        self._message = None
        self._enable = None
        self._direction = None
        # track row and column used in cursor_position
        # initialize to 0,0
        self.row = 0
        self.column = 0
        self._column_align = False
    # pylint: enable-msg=too-many-arguments

    def home(self):
        """Moves the cursor "home" to position (1, 1)."""
        self._write8(_LCD_RETURNHOME)
        time.sleep(0.003)

    def clear(self):
        """Clears everything displayed on the LCD.
        The following example displays, "Hello, world!", then clears the LCD.
        .. code-block:: python
            import time
            import board
            import busio
            import adafruit_character_lcd.character_lcd_i2c as character_lcd
            i2c = busio.I2C(board.SCL, board.SDA)
            lcd = character_lcd.Character_LCD_I2C(i2c, 16, 2)
            lcd.message = "Hello, world!"
            time.sleep(5)
            lcd.clear()
        """
        self._write8(_LCD_CLEARDISPLAY)
        time.sleep(0.003)

    @property
    def column_align(self):
        """If True, message text after '\\n' starts directly below start of first
        character in message. If False, text after '\\n' starts at column zero.
        """
        return self._column_align

    @column_align.setter
    def column_align(self, enable):
        if isinstance(enable, bool):
            self._column_align = enable
        else:
            raise ValueError('The column_align value must be either True or False')

    @property
    def cursor(self):
        """True if cursor is visible. False to stop displaying the cursor.
        The following example shows the cursor after a displayed message:
        .. code-block:: python
            import time
            import board
            import busio
            import adafruit_character_lcd.character_lcd_i2c as character_lcd
            i2c = busio.I2C(board.SCL, board.SDA)
            lcd = character_lcd.Character_LCD_I2C(i2c, 16, 2)
            lcd.cursor = True
            lcd.message = "Cursor! "
            time.sleep(5)
        """
        return self.displaycontrol & _LCD_CURSORON == _LCD_CURSORON

    @cursor.setter
    def cursor(self, show):
        if show:
            self.displaycontrol |= _LCD_CURSORON
        else:
            self.displaycontrol &= ~_LCD_CURSORON
        self._write8(_LCD_DISPLAYCONTROL | self.displaycontrol)

    def cursor_position(self, column, row):
        """Move the cursor to position ``column``, ``row`` for the next
        message only. Displaying a message resets the cursor position to (0, 0).
            :param column: column location
            :param row: row location
        """
        # Clamp row to the last row of the display
        if row >= self.lines:
            row = self.lines - 1
        # Clamp to last column of display
        if column >= self.columns:
            column = self.columns - 1
        # Set location
        self._write8(_LCD_SETDDRAMADDR | (column + _LCD_ROW_OFFSETS[row]))
        # Update self.row and self.column to match setter
        self.row = row
        self.column = column

    @property
    def blink(self):
        """
        Blink the cursor. True to blink the cursor. False to stop blinking.
        The following example shows a message followed by a blinking cursor for five seconds.
        .. code-block:: python
            import time
            import board
            import busio
            import adafruit_character_lcd.character_lcd_i2c as character_lcd
            i2c = busio.I2C(board.SCL, board.SDA)
            lcd = character_lcd.Character_LCD_I2C(i2c, 16, 2)
            lcd.blink = True
            lcd.message = "Blinky cursor!"
            time.sleep(5)
            lcd.blink = False
        """
        return self.displaycontrol & _LCD_BLINKON == _LCD_BLINKON

    @blink.setter
    def blink(self, blink):
        if blink:
            self.displaycontrol |= _LCD_BLINKON
        else:
            self.displaycontrol &= ~_LCD_BLINKON
        self._write8(_LCD_DISPLAYCONTROL | self.displaycontrol)

    @property
    def display(self):
        """
        Enable or disable the display. True to enable the display. False to disable the display.
        The following example displays, "Hello, world!" on the LCD and then turns the display off.
        .. code-block:: python
            import time
            import board
            import busio
            import adafruit_character_lcd.character_lcd_i2c as character_lcd
            i2c = busio.I2C(board.SCL, board.SDA)
            lcd = character_lcd.Character_LCD_I2C(i2c, 16, 2)
            lcd.message = "Hello, world!"
            time.sleep(5)
            lcd.display = False
        """
        return self.displaycontrol & _LCD_DISPLAYON == _LCD_DISPLAYON

    @display.setter
    def display(self, enable):
        if enable:
            self.displaycontrol |= _LCD_DISPLAYON
        else:
            self.displaycontrol &= ~_LCD_DISPLAYON
        self._write8(_LCD_DISPLAYCONTROL | self.displaycontrol)

    @property
    def message(self):
        """Display a string of text on the character LCD.
        Start position is (0,0) if cursor_position is not set.
        If cursor_position is set, message starts at the set
        position from the left for left to right text and from
        the right for right to left text. Resets cursor column
        and row to (0,0) after displaying the message.
        The following example displays, "Hello, world!" on the LCD.
        .. code-block:: python
            import time
            import board
            import busio
            import adafruit_character_lcd.character_lcd_i2c as character_lcd
            i2c = busio.I2C(board.SCL, board.SDA)
            lcd = character_lcd.Character_LCD_I2C(i2c, 16, 2)
            lcd.message = "Hello, world!"
            time.sleep(5)
        """
        return self._message

    @message.setter
    def message(self, message):
        self._message = message
        # Set line to match self.row from cursor_position()
        line = self.row
        # Track times through iteration, to act on the initial character of the message
        initial_character = 0
        # iterate through each character
        for character in message:
            # If this is the first character in the string:
            if initial_character == 0:
                # Start at (0, 0) unless direction is set right to left, in which case start
                # on the opposite side of the display if cursor_position not set or (0,0)
                # If cursor_position is set then starts at the specified location for
                # LEFT_TO_RIGHT. If RIGHT_TO_LEFT cursor_position is determined from right.
                # allows for cursor_position to work in RIGHT_TO_LEFT mode
                if self.displaymode & _LCD_ENTRYLEFT > 0:
                    col = self.column
                else:
                    col = self.columns - 1 - self.column
                self.cursor_position(col, line)
                initial_character += 1
            # If character is \n, go to next line
            if character == '\n':
                line += 1
                # Start the second line at (0, 1) unless direction is set right to left in
                # which case start on the opposite side of the display if cursor_position
                # is (0,0) or not set. Start second line at same column as first line when
                # cursor_position is set
                if self.displaymode & _LCD_ENTRYLEFT > 0:
                    col = self.column * self._column_align
                else:
                    if self._column_align:
                        col = self.column
                    else:
                        col = self.columns - 1
                self.cursor_position(col, line)
            # Write string to display
            else:
                self._write8(ord(character), True)
        # reset column and row to (0,0) after message is displayed
        self.column, self.row = 0, 0

    def move_left(self):
        """Moves displayed text left one column.
        The following example scrolls a message to the left off the screen.
        .. code-block:: python
            import time
            import board
            import busio
            import adafruit_character_lcd.character_lcd_i2c as character_lcd
            i2c = busio.I2C(board.SCL, board.SDA)
            lcd = character_lcd.Character_LCD_I2C(i2c, 16, 2)
            scroll_message = "<-- Scroll"
            lcd.message = scroll_message
            time.sleep(2)
            for i in range(len(scroll_message)):
                lcd.move_left()
                time.sleep(0.5)
        """
        self._write8(_LCD_CURSORSHIFT | _LCD_DISPLAYMOVE | _LCD_MOVELEFT)

    def move_right(self):
        """Moves displayed text right one column.
        The following example scrolls a message to the right off the screen.
        .. code-block:: python
            import time
            import board
            import busio
            import adafruit_character_lcd.character_lcd_i2c as character_lcd
            i2c = busio.I2C(board.SCL, board.SDA)
            lcd = character_lcd.Character_LCD_I2C(i2c, 16, 2)
            scroll_message = "Scroll -->"
            lcd.message = scroll_message
            time.sleep(2)
            for i in range(len(scroll_message) + 16):
                lcd.move_right()
                time.sleep(0.5)
        """
        self._write8(_LCD_CURSORSHIFT | _LCD_DISPLAYMOVE | _LCD_MOVERIGHT)

    @property
    def text_direction(self):
        """The direction the text is displayed. To display the text left to right beginning on the
        left side of the LCD, set ``text_direction = LEFT_TO_RIGHT``. To display the text right
        to left beginning on the right size of the LCD, set ``text_direction = RIGHT_TO_LEFT``.
        Text defaults to displaying from left to right.
        The following example displays "Hello, world!" from right to left.
        .. code-block:: python
            import time
            import board
            import busio
            import adafruit_character_lcd.character_lcd_i2c as character_lcd
            i2c = busio.I2C(board.SCL, board.SDA)
            lcd = character_lcd.Character_LCD_I2C(i2c, 16, 2)
            lcd.text_direction = lcd.RIGHT_TO_LEFT
            lcd.message = "Hello, world!"
            time.sleep(5)
        """
        return self._direction

    @text_direction.setter
    def text_direction(self, direction):
        self._direction = direction
        if direction == self.LEFT_TO_RIGHT:
            self._left_to_right()
        elif direction == self.RIGHT_TO_LEFT:
            self._right_to_left()

    def _left_to_right(self):
        # Displays text from left to right on the LCD.
        self.displaymode |= _LCD_ENTRYLEFT
        self._write8(_LCD_ENTRYMODESET | self.displaymode)

    def _right_to_left(self):
        # Displays text from right to left on the LCD.
        self.displaymode &= ~_LCD_ENTRYLEFT
        self._write8(_LCD_ENTRYMODESET | self.displaymode)

    def create_char(self, location, pattern):
        """
        Fill one of the first 8 CGRAM locations with custom characters.
        The location parameter should be between 0 and 7 and pattern should
        provide an array of 8 bytes containing the pattern. E.g. you can easily
        design your custom character at http://www.quinapalus.com/hd44780udg.html
        To show your custom character use, for example, ``lcd.message = "\x01"``
        :param location: integer in range(8) to store the created character
        :param ~bytes pattern: len(8) describes created character
        """
        # only position 0..7 are allowed
        location &= 0x7
        self._write8(_LCD_SETCGRAMADDR | (location << 3))
        for i in range(8):
            self._write8(pattern[i], char_mode=True)

    def _write8(self, value, char_mode=False):
        # Sends 8b ``value`` in ``char_mode``.
        # :param value: bytes
        # :param char_mode: character/data mode selector. False (default) for
        # data only, True for character bits.
        #  one ms delay to prevent writing too quickly.
        time.sleep(0.001)
        self.interface.send(value, _RS_DATA if char_mode else _RS_INSTRUCTION)
        usleep(50)

    def _pulse_enable(self):
        # Pulses (lo->hi->lo) to send commands.
        self.enable.value = False
        # 1microsec pause
        time.sleep(0.0000001)
        self.enable.value = True
        time.sleep(0.0000001)
        self.enable.value = False
        time.sleep(0.0000001)
# pylint: enable-msg=too-many-instance-attributes


# pylint: disable-msg=too-many-instance-attributes
class Character_LCD_Mono(Character_LCD):

    # pylint: disable-msg=too-many-arguments
    def __init__(self, interface, rs, en, db4, db5, db6, db7, columns, lines,
                 backlight_pin=None, backlight_inverted=False):

        super().__init__(interface, rs, en, db4, db5, db6, db7, columns, lines)
    # pylint: enable-msg=too-many-arguments

    @property
    def backlight(self):
        """Enable or disable backlight. True if backlight is on. False if backlight is off.
        The following example turns the backlight off, then displays, "Hello, world?", then turns
        the backlight on and displays, "Hello, world!"
        .. code-block:: python
            import time
            import board
            import busio
            import adafruit_character_lcd.character_lcd_i2c as character_lcd
            i2c = busio.I2C(board.SCL, board.SDA)
            lcd = character_lcd.Character_LCD_I2C(i2c, 16, 2)
            lcd.backlight = False
            lcd.message = "Hello, world?"
            time.sleep(5)
            lcd.backlight = True
            lcd.message = "Hello, world!"
            time.sleep(5)
        """
        return self._enable

    @backlight.setter
    def backlight(self, enable):
        self._enable = enable
        self.interface.backlight = enable
        self.interface.send(ord(' '), _RS_DATA)

class Character_LCD_I2C_PCF8574(Character_LCD_Mono):
    # pylint: disable=too-few-public-methods, too-many-arguments
    """Character LCD connected to I2C/SPI backpack using its I2C connection.
    This is a subclass of Character_LCD and implements all of the same
    functions and functionality.
    To use, import and initialise as follows:
    .. code-block:: python
        import board
        import busio
        from adafruit_character_lcd.character_lcd_i2c import Character_LCD_I2C_PCF8574
        i2c = busio.I2C(board.SCL, board.SDA)
        lcd = Character_LCD_I2C_PCF8574(i2c, 16, 2)
    """
    def __init__(self, i2c, columns, lines, address=None, backlight_inverted=False):
        """Initialize character LCD connected to backpack using I2C connection
        on the specified I2C bus with the specified number of columns and
        lines on the display. Optionally specify if backlight is inverted.
        """
        from pcf8574 import PCF8574
        if address:
            pcf = PCF8574(i2c, address=address)
        else:
            pcf = PCF8574(i2c)
        super().__init__(pcf, 0, 1, 2, 3, 4, 5,
                         columns, lines)
