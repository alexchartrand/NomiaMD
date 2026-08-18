import { Table } from "facturemd-frontend";

export function ExtractionResults() {
  return (
    <Table>
      <thead>
        <tr>
          <th>Code</th>
          <th>Description</th>
          <th>Confiance</th>
          <th>Tarif</th>
          <th>Citation à l&rsquo;appui</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td className="code">15818</td>
          <td>Visite périodique, patient vulnérable</td>
          <td>92%</td>
          <td>52.30 $</td>
          <td>
            <em>&laquo; Elle vient pour son bilan annuel. &raquo;</em>
          </td>
        </tr>
        <tr>
          <td className="code">08301</td>
          <td>Examen psychosocial</td>
          <td>78%</td>
          <td>31.15 $</td>
          <td>
            <em>&laquo; On a discuté de son anxiété au travail. &raquo;</em>
          </td>
        </tr>
      </tbody>
    </Table>
  );
}
