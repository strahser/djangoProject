from enum import Enum


class EmailType(Enum):
	IN = "Входящие"
	OUT = "Исходящие"

	@classmethod
	def choices(cls):
		return [(i.name, i.value) for i in cls]
