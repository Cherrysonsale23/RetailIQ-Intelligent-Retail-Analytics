import { DatasetDetail } from "@/components/dataset-detail";
export default async function DatasetPage({params}:{params:Promise<{datasetId:string}>}){const {datasetId}=await params;return <DatasetDetail datasetId={datasetId}/>}
