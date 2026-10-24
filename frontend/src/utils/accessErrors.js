export function accessErrorMessage(error) {
  if (error instanceof TypeError || /failed to fetch|networkerror|load failed/i.test(error?.message || '')) {
    return 'Installation injoignable. Réessayez ou utilisez le retour vers Structura Admin.'
  }
  return error?.message || 'Accès indisponible. Réessayez ou revenez à l’écran précédent.'
}
