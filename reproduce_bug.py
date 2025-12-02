
def segundos_para_ass(segundos: float) -> str:
    """Converte segundos para formato ASS (H:MM:SS.CC)"""
    # Arredondar para 2 casas decimais primeiro para evitar erros de precisão
    segundos = round(segundos, 2)
    
    horas = int(segundos // 3600)
    minutos = int((segundos % 3600) // 60)
    secs = segundos % 60
    
    # Correção para caso de arredondamento (ex: 59.996 -> 60.00)
    if secs >= 60:
        secs = 0
        minutos += 1
        if minutos >= 60:
            minutos = 0
            horas += 1
    
    return f"{horas}:{minutos:02d}:{secs:05.2f}"

# Test cases
test_values = [
    59.99,
    59.994,
    59.996,  # Should round to 60.00
    60.0,
    119.996, # Should round to 2:00.00 (displayed as 1:60.00)
]

print("Testing segundos_para_ass:")
for val in test_values:
    res = segundos_para_ass(val)
    print(f"{val} -> {res}")
